FROM python:3.12-slim AS ffmpeg-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    yasm \
    libopus-dev \
    && rm -rf /var/lib/apt/lists/*

ADD https://ffmpeg.org/releases/ffmpeg-7.1.tar.gz /tmp/ffmpeg.tar.gz
RUN tar xf /tmp/ffmpeg.tar.gz -C /tmp &&\
    cd /tmp/ffmpeg-7.1 && \
    ./configure \
      --disable-everything \
      --enable-libopus \
      --enable-decoder=mp3 \
      --enable-decoder=pcm_s16le \
      --enable-muxer=s161e \
      --enable-demuxer=mp3 \
      #uncomment me if you add wav files to sounds
      #--enable-demuxer=wav \
      --enable-protocol=file \
      --enable-protocol=pipe \
      --enable-small \
      --disable-debug \
    && make -j$(nproc) && make install

FROM python:3.14.3-slim AS compile

COPY ./src/resources/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.14.3-slim AS build

WORKDIR /bot

COPY --from=ffmpeg-builder /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=compile /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels /wheels/*.whl
COPY ./src .

CMD ["python", "bot.py"]
