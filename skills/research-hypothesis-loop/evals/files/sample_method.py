from dataclasses import dataclass


@dataclass
class PruningConfig:
    audio_keep_ratio: float = 0.25
    video_keep_ratio: float = 0.25


def select_tokens(audio_scores, video_scores, config):
    audio_count = int(len(audio_scores) * config.audio_keep_ratio)
    video_count = int(len(video_scores) * config.video_keep_ratio)
    audio_indices = sorted(range(len(audio_scores)), key=audio_scores.__getitem__, reverse=True)
    video_indices = sorted(range(len(video_scores)), key=video_scores.__getitem__, reverse=True)
    return audio_indices[:audio_count], video_indices[:video_count]
