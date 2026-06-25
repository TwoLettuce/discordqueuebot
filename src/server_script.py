import discord
from discord.utils import get
from db import get_category_id, set_category_id, get_help_queue_id, set_help_queue_id, set_bot_role_id

async def setup_server(interaction: discord.Interaction):
    """Setup necessary channels, roles, and permissions needed for the bot to function properly.  
    
    Raises:
        PermissionError if the necessary permissions are not granted."""
    _verify_permissions(interaction)
    _save_bot_role_id(interaction)

    await _category_init(interaction)
    category: discord.CategoryChannel = get(interaction.guild.categories, id=get_category_id(interaction.guild.id))
    await _help_queue_channel_init(interaction, category)
    

def _verify_permissions(interaction: discord.Interaction):
    current_permissions: discord.Permissions = interaction.app_permissions
    expected_permissions = [
        ("Manage Channels", current_permissions.manage_channels),
        ("View Channels", current_permissions.read_messages),
        ("Send Messages", current_permissions.send_messages),
        ("Read Message History", current_permissions.read_message_history),
        ("Manage Messages", current_permissions.manage_messages),
        ("Manage Roles", current_permissions.manage_roles),
        ("Connect", current_permissions.connect),
        ("Move Members", current_permissions.move_members),
        ("Speak", current_permissions.speak),
        ("Use Voice Activity", current_permissions.use_voice_activation),
        ("Use Slash Commands", current_permissions.use_application_commands)
    ]

    missing_permissions = [name for name, granted in expected_permissions if not granted]
    
    if not len(missing_permissions) == 0:
        raise PermissionError(f"Missing required permissions: {', '.join(missing_permissions)}")

def _save_bot_role_id(interaction: discord.Interaction):
    for role in interaction.guild.me.roles:
        if role.name != "everyone":
            set_bot_role_id(interaction.guild.id, role.id)

async def _category_init(interaction: discord.Interaction):
    print('category init')
    category_id: int = get_category_id(interaction.guild.id)
    guild_categories = interaction.guild.categories
    help_category = get(guild_categories, id=category_id)
    if help_category is None:
        help_category = await interaction.guild.create_category("Help Queue")
        set_category_id(interaction.guild.id, help_category.id)

    bot_permissions = discord.PermissionOverwrite(move_members=True)
    
    await help_category.set_permissions(interaction.guild.me, overwrite=bot_permissions)

async def _help_queue_channel_init(interaction: discord.Interaction, category: discord.CategoryChannel):
    print("help_queue_channel init")
    help_queue_channel_id = get_help_queue_id(interaction.guild.id)
    channels = category.channels
    help_queue_channel = get(channels, id=help_queue_channel_id)
    if not help_queue_channel:
        help_queue_channel: discord.TextChannel = await category.create_text_channel("help-queue-chat")
        set_help_queue_id(interaction.guild.id, help_queue_channel.id)

    everyone_permissions = discord.PermissionOverwrite(send_messages=False, create_public_threads=False)
    help_queue_channel.set_permissions(interaction.guild.default_role, overwrite=everyone_permissions)

    other_permissions = discord.PermissionOverwrite(send_messages=True)
    for role in interaction.guild.roles:
        if role != interaction.guild.default_role:
            help_queue_channel.set_permissions(role, overwrite=other_permissions)