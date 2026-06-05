"""
============================================================
如何避免漏掉边界情况（本次踩坑复盘）
============================================================

这次最初写的测试没覆盖到"取消 Modal 后无法重选""移除队首应通知新队首"
这类边界问题，根本原因是按"happy path"写测试，而非按"状态机"写测试。

一套可复用的自查清单：

1. 【状态迁移图】
   对每个交互组件，画出它经历的所有状态。
   本例中 Select 的状态：初始未选中 → 选中学生 → 弹出 Modal →
     → 确认 → 学生被移除 ✓
     → 取消 → 回到未选中状态（本次遗漏！Discord 默认做不到）
   每个箭头 = 一个 test case。

2. 【0 / 1 / N 法则】
   每个涉及集合的操作，至少测 3 种数据量：
   - 0：空队列点 Remove Student → 应提示 "Queue is empty."
   - 1：队列只有一人时取消重选（本次遗漏！因为 1 人时 Cancel 是唯一出路）
   - N：多人时选中间的人、选队首、选队尾

3. 【"反悔"路径】
   任何需要用户确认的操作，必须测"点了确认再取消"的路径：
   - 点了删除 → Modal 弹出 → 按 Esc 关闭 → 还能重新选吗？
   - 本次的 Cancel 选项就是为了给这个路径兜底

4. 【副作用传播】
   操作 A 影响了谁？列出所有"利益相关方"：
   - 被移除的学生本人 → 应收到 DM
   - 新队首 → 应收到 "you are next"（本次遗漏！）
   - 其他 TA → 他们打开的下拉菜单里该项应失效（已测）

5. 【并发 / 竞赛】
   两个 TA 同时操作同一学生：
   - TA1 选中 Alice，弹出 Modal 但不提交
   - TA2 也选中 Alice，确认移除
   - TA1 再点确认 → 应提示 "已不在队列中"（已测）
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime

import discord

from records import QueueEntry
from help_queue import HelpQueue


# ==========================================================
# Fixtures
# ==========================================================

def make_entry(user_id: int, username: str = "", student_name: str = "",
               details: str = "", is_passoff: bool = False, in_person: bool = False):
    return QueueEntry(
        user_id=user_id,
        username=username or f"user_{user_id}",
        student_name=student_name,
        details=details,
        is_passoff=is_passoff,
        timestamp=datetime.now(),
        in_person=in_person,
    )


def make_mock_interaction(queue: HelpQueue, user_id: int = 999,
                          display_name: str = "TA_Test"):
    """构造一个带 client.queue 的 mock Interaction"""
    mock = MagicMock(spec=discord.Interaction)
    mock.client = MagicMock()
    mock.client.queue = queue
    mock.user = MagicMock()
    mock.user.id = user_id
    mock.user.display_name = display_name
    mock.response = MagicMock()
    mock.response.send_message = AsyncMock()
    mock.response.send_modal = AsyncMock()
    mock.response.defer = AsyncMock()
    mock.followup = MagicMock()
    mock.followup.send = AsyncMock()
    return mock



# ==========================================================
# HelpQueue
# ==========================================================

class TestHelpQueue(unittest.IsolatedAsyncioTestCase):

    async def test_remove_existing_user(self):
        q = HelpQueue()
        await q.add(make_entry(1))
        await q.add(make_entry(2))
        await q.remove(1)
        self.assertEqual(len(q.entries), 1)
        self.assertEqual(q.entries[0].user_id, 2)

    async def test_remove_nonexistent_user_does_nothing(self):
        q = HelpQueue()
        await q.add(make_entry(1))
        await q.remove(999)
        self.assertEqual(len(q.entries), 1)

    async def test_remove_from_empty_queue(self):
        q = HelpQueue()
        await q.remove(1)
        self.assertEqual(len(q.entries), 0)

    async def test_get_front_after_remove(self):
        q = HelpQueue()
        await q.add(make_entry(1))
        await q.add(make_entry(2))
        self.assertEqual((await q.get_front()).user_id, 1)
        await q.remove(1)
        self.assertEqual((await q.get_front()).user_id, 2)

    async def test_get_front_empty_queue(self):
        q = HelpQueue()
        self.assertIsNone(await q.get_front())


# ==========================================================
# RemoveStudentView — 构造
# ==========================================================

class TestRemoveStudentViewConstruction(unittest.IsolatedAsyncioTestCase):

    def test_options_include_cancel_first(self):
        from ui.views.ta_view import RemoveStudentView
        view = RemoveStudentView([make_entry(1, username="alice")])
        select = view.children[0]
        self.assertEqual(select.options[0].value, "__cancel__")
        self.assertEqual(select.options[0].label, "— Cancel —")

    def test_emoji_passoff_vs_question(self):
        from ui.views.ta_view import RemoveStudentView
        entries = [
            make_entry(1, username="a", is_passoff=True),
            make_entry(2, username="b", is_passoff=False),
        ]
        view = RemoveStudentView(entries)
        select = view.children[0]
        self.assertEqual(select.options[1].emoji.name, "✅")
        self.assertEqual(select.options[2].emoji.name, "❓")

    def test_label_prefers_student_name(self):
        from ui.views.ta_view import RemoveStudentView
        view = RemoveStudentView([make_entry(1, username="discord_abc", student_name="张三")])
        self.assertEqual(view.children[0].options[1].label, "张三")

    def test_label_falls_back_to_username(self):
        from ui.views.ta_view import RemoveStudentView
        view = RemoveStudentView([make_entry(1, username="discord_abc", student_name="")])
        self.assertEqual(view.children[0].options[1].label, "discord_abc")

    def test_label_truncated_at_100_chars(self):
        from ui.views.ta_view import RemoveStudentView
        view = RemoveStudentView([make_entry(1, username="x", student_name="A" * 150)])
        opt = view.children[0].options[1]
        self.assertLessEqual(len(opt.label), 100)
        self.assertTrue(opt.label.endswith("..."))

    def test_description_truncated(self):
        """description ≤ 100 字符（含 "#N " 前缀）"""
        from ui.views.ta_view import RemoveStudentView
        view = RemoveStudentView([make_entry(1, username="x", details="D" * 200)])
        opt = view.children[0].options[1]
        self.assertLessEqual(len(opt.description), 100)

    def test_value_is_user_id_string(self):
        from ui.views.ta_view import RemoveStudentView
        view = RemoveStudentView([make_entry(123456, username="alice")])
        self.assertEqual(view.children[0].options[1].value, "123456")


# ==========================================================
# RemoveStudentView — select_callback
# ==========================================================

class TestRemoveStudentViewCallback(unittest.IsolatedAsyncioTestCase):

    async def test_cancel_option_defers_and_returns(self):
        """选 Cancel → defer，不弹 Modal"""
        from ui.views.ta_view import RemoveStudentView
        q = HelpQueue()
        await q.add(make_entry(1, username="alice"))

        interaction = make_mock_interaction(q)
        view = RemoveStudentView(q.entries)

        with patch.object(discord.ui.Select, 'values',
                          new_callable=PropertyMock) as mock_values:
            mock_values.return_value = ["__cancel__"]
            await view.select_callback(interaction)

        interaction.response.defer.assert_awaited_once()
        interaction.response.send_modal.assert_not_awaited()

    async def test_select_student_sends_modal(self):
        """选学生 → 弹出 RemoveConfirmModal，携带正确参数"""
        from ui.views.ta_view import RemoveStudentView
        q = HelpQueue()
        await q.add(make_entry(1, username="alice", student_name="Alice"))

        interaction = make_mock_interaction(q)
        view = RemoveStudentView(q.entries)

        with patch.object(discord.ui.Select, 'values',
                          new_callable=PropertyMock) as mock_values:
            mock_values.return_value = ["1"]
            await view.select_callback(interaction)

        interaction.response.send_modal.assert_awaited_once()
        modal = interaction.response.send_modal.call_args[0][0]
        self.assertEqual(modal.student_user_id, 1)
        self.assertEqual(modal.student_name, "Alice")

    async def test_student_already_removed_by_another_ta(self):
        """并发：选中的学生已被其他 TA 移除"""
        from ui.views.ta_view import RemoveStudentView
        q = HelpQueue()
        # entry 不在队列中（模拟已移除）
        entry = make_entry(2, username="bob")

        interaction = make_mock_interaction(q)
        view = RemoveStudentView([entry])

        with patch.object(discord.ui.Select, 'values',
                          new_callable=PropertyMock) as mock_values:
            mock_values.return_value = ["2"]
            await view.select_callback(interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        self.assertIn("no longer in the queue", msg)


# ==========================================================
# RemoveConfirmModal
# ==========================================================

class TestRemoveConfirmModal(unittest.IsolatedAsyncioTestCase):

    def test_init_stores_user_id_and_display_name(self):
        from ui.modals import RemoveConfirmModal
        modal = RemoveConfirmModal(123, "Alice")
        self.assertEqual(modal.student_user_id, 123)
        self.assertEqual(modal.student_name, "Alice")

    async def test_on_submit_removes_student(self):
        from ui.modals import RemoveConfirmModal
        q = HelpQueue()
        await q.add(make_entry(1, username="alice"))
        await q.add(make_entry(2, username="bob"))

        interaction = make_mock_interaction(q)
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.display_name = "alice"
        mock_user.send = AsyncMock()
        interaction.client.fetch_user = AsyncMock(return_value=mock_user)

        with patch("ui.modals.update_queue_messages", AsyncMock()), \
             patch("ui.modals.notify_next_if_changed", AsyncMock()):
            modal = RemoveConfirmModal(1, "Alice")
            await modal.on_submit(interaction)

        self.assertEqual(len(q.entries), 1)
        self.assertEqual(q.entries[0].user_id, 2)

    async def test_on_submit_notifies_new_front(self):
        """移除队首 → notify_next_if_changed 被调用，传入旧队首"""
        from ui.modals import RemoveConfirmModal
        q = HelpQueue()
        await q.add(make_entry(1, username="alice"))
        await q.add(make_entry(2, username="bob"))

        interaction = make_mock_interaction(q)
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.display_name = "alice"
        mock_user.send = AsyncMock()
        interaction.client.fetch_user = AsyncMock(return_value=mock_user)

        with patch("ui.modals.update_queue_messages", AsyncMock()), \
             patch("ui.modals.notify_next_if_changed", AsyncMock()) as mock_notify:
            modal = RemoveConfirmModal(1, "Alice")
            await modal.on_submit(interaction)

        mock_notify.assert_awaited_once()
        # 第二个参数 front_before 是旧队首（alice, user_id=1）
        self.assertEqual(mock_notify.call_args[0][1].user_id, 1)

    async def test_on_submit_no_notify_when_removed_not_front(self):
        """移除非队首 → notify_next_if_changed 仍被调用，但传入的旧队首没变"""
        from ui.modals import RemoveConfirmModal
        q = HelpQueue()
        await q.add(make_entry(1, username="alice"))
        await q.add(make_entry(2, username="bob"))

        interaction = make_mock_interaction(q)
        mock_user = MagicMock()
        mock_user.id = 2
        mock_user.display_name = "bob"
        mock_user.send = AsyncMock()
        interaction.client.fetch_user = AsyncMock(return_value=mock_user)

        with patch("ui.modals.update_queue_messages", AsyncMock()), \
             patch("ui.modals.notify_next_if_changed", AsyncMock()) as mock_notify:
            modal = RemoveConfirmModal(2, "Bob")
            await modal.on_submit(interaction)

        mock_notify.assert_awaited_once()
        # 旧队首是 alice (user_id=1)，与移除的 bob (user_id=2) 不同，
        # notify_next_if_changed 内部判断前后队首都是 alice，因此不发 DM
        self.assertEqual(mock_notify.call_args[0][1].user_id, 1)

    async def test_on_submit_dm_to_student(self):
        from ui.modals import RemoveConfirmModal
        q = HelpQueue()
        await q.add(make_entry(1, username="alice"))

        interaction = make_mock_interaction(q)
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.display_name = "alice"
        mock_user.send = AsyncMock()
        interaction.client.fetch_user = AsyncMock(return_value=mock_user)

        with patch("ui.modals.update_queue_messages", AsyncMock()), \
             patch("ui.modals.notify_next_if_changed", AsyncMock()):
            modal = RemoveConfirmModal(1, "Alice")
            await modal.on_submit(interaction)

        mock_user.send.assert_awaited_once()
        self.assertIn("removed from the CS240 help queue", mock_user.send.call_args[0][0])

    async def test_on_submit_dm_includes_reason(self):
        from ui.modals import RemoveConfirmModal
        q = HelpQueue()
        await q.add(make_entry(1, username="alice"))

        interaction = make_mock_interaction(q)
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.display_name = "alice"
        mock_user.send = AsyncMock()
        interaction.client.fetch_user = AsyncMock(return_value=mock_user)

        with patch("ui.modals.update_queue_messages", AsyncMock()), \
             patch("ui.modals.notify_next_if_changed", AsyncMock()):
            modal = RemoveConfirmModal(1, "Alice")
            modal.reason = MagicMock()
            modal.reason.value = "Asked too many questions"
            await modal.on_submit(interaction)

        dm_text = mock_user.send.call_args[0][0]
        self.assertIn("Reason:", dm_text)
        self.assertIn("Asked too many questions", dm_text)

    async def test_on_submit_success_message(self):
        from ui.modals import RemoveConfirmModal
        q = HelpQueue()
        await q.add(make_entry(1, username="alice"))

        interaction = make_mock_interaction(q)
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.display_name = "alice"
        mock_user.send = AsyncMock()
        interaction.client.fetch_user = AsyncMock(return_value=mock_user)
        interaction.response.send_message = AsyncMock()

        with patch("ui.modals.update_queue_messages", AsyncMock()), \
             patch("ui.modals.notify_next_if_changed", AsyncMock()):
            modal = RemoveConfirmModal(1, "Alice")
            await modal.on_submit(interaction)

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        self.assertIn("has been removed from the queue by", msg)


# ==========================================================
# TAView.remove_from_queue 按钮
# ==========================================================

class TestTAViewRemoveButton(unittest.IsolatedAsyncioTestCase):

    async def test_empty_queue_shows_message(self):
        from ui.views.ta_view import TAView
        q = HelpQueue()
        interaction = make_mock_interaction(q)
        view = TAView()

        for item in view.children:
            if item.custom_id == "remove_from_queue":
                await item.callback(interaction)
                break

        interaction.response.send_message.assert_awaited_once()
        msg = interaction.response.send_message.call_args[0][0]
        self.assertEqual(msg, "Queue is empty.")

    async def test_nonempty_queue_shows_select_with_legend(self):
        from ui.views.ta_view import TAView, RemoveStudentView
        q = HelpQueue()
        await q.add(make_entry(1, username="alice"))

        interaction = make_mock_interaction(q)
        view = TAView()

        for item in view.children:
            if item.custom_id == "remove_from_queue":
                await item.callback(interaction)
                break

        interaction.response.send_message.assert_awaited_once()
        sent_view = interaction.response.send_message.call_args[1]["view"]
        self.assertIsInstance(sent_view, RemoveStudentView)
        text = interaction.response.send_message.call_args[0][0]
        self.assertIn("✅", text)
        self.assertIn("❓", text)
        self.assertIn("Passoff", text)
        self.assertIn("Question", text)


if __name__ == "__main__":
    unittest.main()
