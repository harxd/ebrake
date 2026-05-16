import subprocess
import json
import re
import os
import time

class Transcoder:
    def __init__(self, ffmpeg_bin="ffmpeg", ffprobe_bin="ffprobe"):
        self.ffmpeg_bin = ffmpeg_bin
        self.ffprobe_bin = ffprobe_bin

    def get_info(self, file_path):
        cmd = [
            self.ffprobe_bin, "-v", "quiet",
            "-print_format", "json", "-show_streams", "-show_format",
            file_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except:
            return None

    def build_command(self, input_path, output_path, config):
        info = self.get_info(input_path)
        if not info:
            raise Exception("Could not probe file")

        # Map sections
        out_cfg = config.get('output', {})
        vid_cfg = config.get('video', {})
        aud_cfg = config.get('audio', {})

        cmd = [self.ffmpeg_bin, "-i", input_path, "-y"]

        # Video Settings
        codec = vid_cfg.get('codec', 'libsvtav1')
        cmd += ["-c:v", codec]
        if vid_cfg.get('preset'): cmd += ["-preset", str(vid_cfg.get('preset'))]
        if vid_cfg.get('crf'): cmd += ["-crf", str(vid_cfg.get('crf'))]
        
        tune = vid_cfg.get('tune')
        if tune and tune != "":
            if codec == 'libsvtav1':
                cmd += ["-svtav1-params", f"tune={tune}"]
            elif not tune.isdigit(): # libx264/x265 don't support numeric tunes like "0"
                cmd += ["-tune", tune]
        
        if vid_cfg.get('pix_fmt'): cmd += ["-pix_fmt", vid_cfg.get('pix_fmt')]
        
        fps_mode = vid_cfg.get('fps_mode', 'cfr')
        if fps_mode == 'cfr': cmd += ["-fps_mode", "cfr"]
        else: cmd += ["-fps_mode", "vfr"]

        # Audio Settings (Passthrough Logic)
        pt_codecs = [c.strip() for c in aud_cfg.get('passthrough_codecs', '').split(',') if c.strip()]
        fallback_codec = aud_cfg.get('fallback_codec', 'libopus')
        fallback_bitrate = aud_cfg.get('fallback_bitrate', '128k')

        audio_streams = [s for s in info.get('streams', []) if s['codec_type'] == 'audio']
        
        for i, stream in enumerate(audio_streams):
            codec_name = stream.get('codec_name', '')
            if codec_name in pt_codecs:
                cmd += [f"-c:a:{i}", "copy"]
            else:
                cmd += [f"-c:a:{i}", fallback_codec, f"-b:a:{i}", fallback_bitrate]

        # Subtitles (copy all by default)
        cmd += ["-c:s", "copy"]
        
        # Output
        cmd += ["-progress", "pipe:1", output_path]
        return cmd

    def run(self, cmd, progress_callback):
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

        full_log = []
        duration = 0
        for line in process.stdout:
            full_log.append(line)
            
            if "Duration:" in line and not duration:
                match = re.search(r"Duration:\s+(\d+):(\d+):(\d+\.\d+)", line)
                if match:
                    h, m, s = match.groups()
                    duration = int(h)*3600 + int(m)*60 + float(s)

            if "out_time_ms=" in line:
                try:
                    raw_val = line.split('=')[1].strip()
                    if raw_val != "N/A":
                        ms = int(raw_val)
                        cur_time = ms / 1000000.0
                        if duration > 0:
                            progress = min(99.9, (cur_time / duration) * 100)
                            progress_callback(progress)
                except (ValueError, IndexError):
                    pass

        process.wait()
        if process.returncode == 0:
            progress_callback(100)
            return True, ""
        
        # Return the last 30 lines of the log for debugging
        error_msg = "".join(full_log[-30:])
        return False, error_msg
