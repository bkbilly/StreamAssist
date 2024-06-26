import asyncio
import logging

import av
from av.audio.resampler import AudioResampler
from av.container.input import InputContainer

_LOGGER = logging.getLogger(__name__)


class Stream:
    def __init__(self):
        self.closed: bool = False
        self.container: InputContainer | None = None
        self.enabled: bool = False
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    def open(self, file: str, allow_all_mediatypes: bool, **kwargs):
        if "options" not in kwargs:
            kwargs["options"] = {
                "fflags": "nobuffer",
                "flags": "low_delay",
                "timeout": "5000000",
            }

            if file.startswith("rtsp"):
                kwargs["options"]["rtsp_flags"] = "prefer_tcp"
                if not allow_all_mediatypes:
                    kwargs["options"]["allowed_media_types"] = "audio"

        kwargs.setdefault("timeout", 5)
        _LOGGER.debug("Starting stream with kwargs: %s", kwargs)

        try:
            # https://pyav.org/docs/9.0.2/api/_globals.html
            self.container = av.open(file, **kwargs)
            _LOGGER.info("Stream started")
        except Exception as e:
            _LOGGER.error("Can't open stream: %s", e)

    def run(self, end=True):
        _LOGGER.info("stream start")

        resampler = AudioResampler(format="s16", layout="mono", rate=16000)

        try:
            for frame in self.container.decode(audio=0):
                if self.closed:
                    return
                if not self.enabled:
                    continue
                for frame_raw in resampler.resample(frame):
                    chunk = frame_raw.to_ndarray().tobytes()
                    self.queue.put_nowait(chunk)
        except Exception as e:
            _LOGGER.error(f"stream exception {type(e)}: {e}")
        finally:
            self.container.close()
            self.container = None

        if end and self.enabled:
            self.queue.put_nowait(b"")

        _LOGGER.info("stream end")

    def close(self):
        _LOGGER.info(f"stream close")
        self.closed = True

    def start(self):
        while self.queue.qsize():
            self.queue.get_nowait()

        self.enabled = True

    def stop(self):
        self.enabled = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        return await self.queue.get()
