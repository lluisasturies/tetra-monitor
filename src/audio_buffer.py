import queue
import sounddevice as sd
import soundfile as sf
import threading
import os

class AudioBuffer:
    def __init__(self, device_index, sample_rate, channels, prebuffer_seconds, output_dir):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.prebuffer_seconds = prebuffer_seconds
        self.output_dir = output_dir
        self.buffer = queue.Queue(maxsize=prebuffer_seconds*sample_rate)
        self.recording = False
        self.frames = []
        os.makedirs(self.output_dir, exist_ok=True)

    def start_buffer(self):
        def callback(indata, frames, time_info, status):
            if self.buffer.full():
                self.buffer.get()
            self.buffer.put(indata.copy())
            if self.recording:
                self.frames.append(indata.copy())

        self.stream = sd.InputStream(
            device=self.device_index,
            channels=self.channels,
            samplerate=self.sample_rate,
            callback=callback
        )
        self.stream.start()

    def start_recording(self):
        self.recording = True
        self.frames = list(self.buffer.queue)  # pre-buffer

    def stop_recording(self, filename):
        self.recording = False
        filepath = os.path.join(self.output_dir, filename)
        if self.frames:
            sf.write(filepath, self.sample_rate, self.frames, format='FLAC')
        return filepath