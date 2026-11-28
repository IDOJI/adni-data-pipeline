"""Shared display formatting; numeric measurements and their scopes stay separate."""
import math

FORMAT_VERSION = 'explicit-units-v1'


def format_duration(seconds):
    """Show explicit units, retain hours above 24, and never turn unknown into zero."""
    if seconds is None:return '미완료'
    if not math.isfinite(float(seconds)) or seconds<0:raise ValueError('Invalid duration')
    whole=int(math.floor(float(seconds)+.5));hours,left=divmod(whole,3600);minutes,secs=divmod(left,60)
    return f'{hours}시간 {minutes}분 {secs}초'
