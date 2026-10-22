# MIT License

# Copyright (c) 2020 Netherlands Film Academy

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Preview window that is shown after a playblast/flipbook has been rendered.

It plays back the rendered JPG frames (frame accurate, no codec dependencies)
and asks the artist whether the result should be submitted to ShotGrid.
The movie with slate is rendered in the background (MovieJob) while the artist
watches, so the window opens right after the playblast is done.
"""

import bisect
import collections
import os
import re
import subprocess
import sys
import threading
import time

try:
    from PySide2 import QtCore, QtGui, QtWidgets
except ModuleNotFoundError:
    from PySide6 import QtCore, QtGui, QtWidgets

# Optional: used to play the scene's sound in the preview
try:
    try:
        from PySide2 import QtMultimedia
    except ModuleNotFoundError:
        from PySide6 import QtMultimedia
except Exception:
    QtMultimedia = None


_FRAME_RE = re.compile(r"\.(-?\d+)\.jpe?g$", re.IGNORECASE)

# Rough memory budget for decoded frames kept in memory (bytes)
_CACHE_BUDGET = 400 * 1024 * 1024

# --- Theme ---
_BG = "#1b1c1f"
_SURFACE = "#25272b"
_SURFACE_HOVER = "#2f3237"
_BORDER = "#34373d"
_TEXT = "#e6e7ea"
_TEXT_MUTED = "#8b8f98"
_ACCENT = "#3b82f6"
_ACCENT_HOVER = "#5a97f8"
_ACCENT_PRESSED = "#2f6ad0"

_STYLESHEET = """
QDialog#PreviewDialog {{
    background-color: {bg};
}}
QDialog#PreviewDialog QLabel {{
    color: {text};
    background: transparent;
}}
QDialog#PreviewDialog QLabel#Title {{
    font-size: 15px;
    font-weight: 600;
}}
QDialog#PreviewDialog QLabel#Muted, QDialog#PreviewDialog QLabel#FrameTotal {{
    color: {muted};
}}
QDialog#PreviewDialog QLabel#Error {{
    color: #f87171;
}}
QDialog#PreviewDialog QLabel#Success {{
    color: #4ade80;
}}
QDialog#PreviewDialog QLabel#FrameNumber {{
    font-size: 15px;
    font-weight: 600;
}}
QDialog#PreviewDialog QLabel#Chip {{
    color: {muted};
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 2px 9px;
    font-size: 11px;
}}
QFrame#Transport, QFrame#Footer {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 10px;
}}
QToolButton#IconButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 4px;
}}
QToolButton#IconButton:hover {{
    background-color: {surface_hover};
}}
QToolButton#IconButton:checked {{
    background-color: rgba(59, 130, 246, 0.22);
}}
QToolButton#IconButton:disabled {{
    background: transparent;
}}
QToolButton#PlayButton {{
    background-color: {text};
    border: none;
    border-radius: 18px;
}}
QToolButton#PlayButton:hover {{
    background-color: #ffffff;
}}
QToolButton#PlayButton:disabled {{
    background-color: {border};
}}
QSlider#Timeline::groove:horizontal {{
    height: 4px;
    background: {border};
    border-radius: 2px;
}}
QSlider#Timeline::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}
QSlider#Timeline::handle:horizontal {{
    background: {text};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider#Timeline::handle:horizontal:hover {{
    background: #ffffff;
}}
QPushButton#SecondaryButton, QPushButton#GhostButton {{
    color: {text};
    background-color: transparent;
    border: 1px solid {border};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 500;
}}
QPushButton#SecondaryButton:hover, QPushButton#GhostButton:hover {{
    background-color: {surface_hover};
}}
QPushButton#GhostButton {{
    padding: 6px 12px;
}}
QPushButton#GhostButton:disabled {{
    color: {muted};
}}
QPushButton#PrimaryButton {{
    color: #ffffff;
    background-color: {accent};
    border: none;
    border-radius: 8px;
    padding: 9px 18px;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background-color: {accent_hover};
}}
QPushButton#PrimaryButton:pressed {{
    background-color: {accent_pressed};
}}
QPushButton#PrimaryButton:disabled {{
    color: {muted};
    background-color: {border};
}}
QToolTip {{
    color: {text};
    background-color: {surface};
    border: 1px solid {border};
    padding: 4px;
}}
""".format(
    bg=_BG,
    surface=_SURFACE,
    surface_hover=_SURFACE_HOVER,
    border=_BORDER,
    text=_TEXT,
    muted=_TEXT_MUTED,
    accent=_ACCENT,
    accent_hover=_ACCENT_HOVER,
    accent_pressed=_ACCENT_PRESSED,
)


def find_frames(folder):
    """
    Find the rendered JPG frames in a folder.

    :param str folder:  Folder containing the rendered frames
    :returns:           List of (frame_number, path) tuples, sorted by frame
    :rtype:             list
    """
    frames = []
    if not folder or not os.path.isdir(folder):
        return frames

    for entry in os.scandir(folder):
        if not entry.is_file():
            continue
        match = _FRAME_RE.search(entry.name)
        if match:
            frames.append((int(match.group(1)), entry.path))

    frames.sort()
    return frames


def _make_icon(kind, color, size=20):
    """
    Draw a simple vector icon, so we don't depend on icon files or fonts.

    :param str kind:    play, pause, prev, next, loop or open
    :param str color:   Icon color
    :param int size:    Icon size in logical pixels
    """
    scale = 3  # draw at a higher resolution so it stays sharp on HiDPI screens
    pixmap = QtGui.QPixmap(size * scale, size * scale)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.scale(scale * size / 24.0, scale * size / 24.0)  # 24x24 design grid
    qcolor = QtGui.QColor(color)
    pen = QtGui.QPen(qcolor, 2.0)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)

    def triangle(x0, x1, top, bottom):
        path = QtGui.QPainterPath()
        path.moveTo(x0, top)
        path.lineTo(x1, (top + bottom) / 2.0)
        path.lineTo(x0, bottom)
        path.closeSubpath()
        return path

    if kind == "play":
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(qcolor)
        painter.drawPath(triangle(8.0, 19.0, 5.0, 19.0))
    elif kind == "pause":
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(qcolor)
        painter.drawRoundedRect(QtCore.QRectF(6.5, 5.5, 4, 13), 1.2, 1.2)
        painter.drawRoundedRect(QtCore.QRectF(13.5, 5.5, 4, 13), 1.2, 1.2)
    elif kind in ("prev", "next"):
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(qcolor)
        if kind == "next":
            painter.drawPath(triangle(6.0, 15.0, 6.0, 18.0))
            painter.drawRoundedRect(QtCore.QRectF(15.5, 6, 2.5, 12), 1, 1)
        else:
            painter.drawPath(triangle(18.0, 9.0, 6.0, 18.0))
            painter.drawRoundedRect(QtCore.QRectF(6.0, 6, 2.5, 12), 1, 1)
    elif kind == "loop":
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        path = QtGui.QPainterPath()
        path.moveTo(17, 5)
        path.lineTo(20, 8)
        path.lineTo(17, 11)
        path.moveTo(4, 12)
        path.lineTo(4, 11)
        path.quadTo(4, 8, 7, 8)
        path.lineTo(20, 8)
        path.moveTo(7, 19)
        path.lineTo(4, 16)
        path.lineTo(7, 13)
        path.moveTo(20, 12)
        path.lineTo(20, 13)
        path.quadTo(20, 16, 17, 16)
        path.lineTo(4, 16)
        painter.drawPath(path)
    elif kind in ("sound", "mute"):
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(qcolor)
        speaker = QtGui.QPainterPath()
        speaker.moveTo(3, 9.5)
        speaker.lineTo(7, 9.5)
        speaker.lineTo(12, 5)
        speaker.lineTo(12, 19)
        speaker.lineTo(7, 14.5)
        speaker.lineTo(3, 14.5)
        speaker.closeSubpath()
        painter.drawPath(speaker)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        if kind == "sound":
            painter.drawArc(QtCore.QRectF(10, 8, 8, 8), -60 * 16, 120 * 16)
            painter.drawArc(QtCore.QRectF(9, 4.5, 13, 15), -60 * 16, 120 * 16)
        else:
            painter.drawLine(QtCore.QPointF(15.5, 9), QtCore.QPointF(21, 15))
            painter.drawLine(QtCore.QPointF(21, 9), QtCore.QPointF(15.5, 15))
    elif kind == "open":
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        path = QtGui.QPainterPath()
        path.moveTo(18, 13)
        path.lineTo(18, 18)
        path.quadTo(18, 20, 16, 20)
        path.lineTo(6, 20)
        path.quadTo(4, 20, 4, 18)
        path.lineTo(4, 8)
        path.quadTo(4, 6, 6, 6)
        path.lineTo(11, 6)
        path.moveTo(14, 4)
        path.lineTo(20, 4)
        path.lineTo(20, 10)
        path.moveTo(10, 14)
        path.lineTo(20, 4)
        painter.drawPath(path)

    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return QtGui.QIcon(pixmap)


class MovieJob(QtCore.QObject):
    """
    Runs a blocking function (rendering the slate/movie) on a worker thread.

    The function must not touch the host application's API (maya.cmds, hou, ...).
    ``finished(success, error)`` is emitted when done, delivered on the main thread.
    """

    finished = QtCore.Signal(bool, str)

    def __init__(self, func, output_path, parent=None):
        QtCore.QObject.__init__(self, parent)
        self._func = func
        self.output_path = output_path
        self.success = None
        self.error = ""
        self._done = threading.Event()
        self._thread = None
        self._start_time = None

    def start(self):
        self._start_time = time.time()
        self._thread = threading.Thread(
            target=self._run, name="ReviewSubmissionMovieJob"
        )
        self._thread.daemon = True
        self._thread.start()

    def _run(self):
        success = False
        error = ""
        try:
            self._func()
            # the movie must exist and be (re)written by this job
            if not os.path.isfile(self.output_path):
                error = "The movie was not created."
            elif os.path.getmtime(self.output_path) < self._start_time - 2:
                error = "The movie was not updated."
            else:
                success = True
        except Exception as err:
            message = err.args[0] if err.args else err
            if isinstance(message, bytes):
                message = message.decode("utf-8", "replace")
            error = str(message).strip() or err.__class__.__name__

        self.success = success
        self.error = error
        self._done.set()
        self.finished.emit(success, error)

    def is_running(self):
        return self._thread is not None and not self._done.is_set()

    def wait(self, timeout=None):
        """Wait for the job to finish. Returns True when it's done."""
        if self._thread is None:
            return True
        return self._done.wait(timeout)


class _AudioTrack(QtCore.QObject):
    """
    Plays the scene's sound and acts as the master clock for the picture.

    Frame ``offset`` is the scene frame where the sound starts (Maya's audio
    node ``offset``). While the sound is running, the picture follows the
    sound's position (like a real video player), so picture and sound can't
    drift apart and the start-up latency of the sound doesn't matter.

    States: idle -> starting (asked to play, waiting for the sound to really
    run) -> running (clock) -> ended (sound finished before the picture).
    """

    failed = QtCore.Signal(str)

    # maximum interpolation between two position updates (ms)
    MAX_INTERPOLATION = 250

    def __init__(self, path, offset, fps, parent=None):
        QtCore.QObject.__init__(self, parent)
        self.path = path
        self.offset = float(offset or 0)
        self.fps = float(fps)
        self.error = ""
        self._player = None
        self._output = None
        self._qt6 = False
        self.state = "idle"
        self._seek_pos = 0
        self._start_clock = QtCore.QElapsedTimer()
        self._pos_clock = QtCore.QElapsedTimer()
        self._last_pos = None
        self._last_frame = None

        if QtMultimedia is None:
            self.error = "Sound playback is not available in this application."
            return
        if not path or not os.path.isfile(path):
            self.error = "Sound file not found: %s" % (path or "-")
            return

        try:
            player = QtMultimedia.QMediaPlayer(self)
            url = QtCore.QUrl.fromLocalFile(path)
            if hasattr(QtMultimedia, "QAudioOutput") and hasattr(
                player, "setAudioOutput"
            ):
                # Qt 6
                self._qt6 = True
                self._output = QtMultimedia.QAudioOutput(self)
                player.setAudioOutput(self._output)
                player.errorOccurred.connect(self._on_error)
                player.setSource(url)
            else:
                # Qt 5
                player.error.connect(self._on_error)
                player.setMedia(QtMultimedia.QMediaContent(url))
            self._player = player
        except Exception as err:
            self._player = None
            self.error = "Could not load the sound: %s" % err

    @property
    def available(self):
        return self._player is not None

    def _on_error(self, *args):
        message = ""
        try:
            message = self._player.errorString()
        except Exception:
            pass
        self.error = "Could not play the sound: %s" % (message or "unknown error")
        self.stop()
        self._player = None
        self.failed.emit(self.error)

    def _is_playing(self):
        player = self._player
        if self._qt6:
            state = player.playbackState()
            return state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState
        return player.state() == QtMultimedia.QMediaPlayer.State.PlayingState

    def _is_loaded(self):
        status = self._player.mediaStatus()
        names = ("LoadedMedia", "BufferingMedia", "BufferedMedia", "EndOfMedia")
        enum = getattr(QtMultimedia.QMediaPlayer, "MediaStatus", QtMultimedia.QMediaPlayer)
        return any(status == getattr(enum, name, None) for name in names)

    def set_muted(self, muted):
        if not self.available:
            return
        if self._output is not None:
            self._output.setMuted(muted)
        else:
            self._player.setMuted(muted)

    def _target_ms(self, frame):
        return (frame - self.offset) / self.fps * 1000.0

    def covers(self, frame):
        """True if the sound has audio at this scene frame."""
        if not self.available:
            return False
        target = self._target_ms(frame)
        duration = self._player.duration()
        return target >= 0 and (duration <= 0 or target < duration - 20)

    def start_at(self, frame):
        """
        Start the sound at a scene frame.

        :returns:   True if the sound is starting (the picture should wait for it)
        """
        if not self.available or not self._is_loaded():
            return False
        self._seek_pos = int(max(self._target_ms(frame), 0))
        self._player.setPosition(self._seek_pos)
        self._player.play()
        self.state = "starting"
        self._start_clock.start()
        self._last_pos = None
        self._last_frame = None
        return True

    def start_elapsed(self):
        """Milliseconds since start_at() was called."""
        return self._start_clock.elapsed() if self._start_clock.isValid() else 0

    def pause(self):
        """Pause the sound and forget where it was (the picture decides)."""
        if self.available and self._is_playing():
            self._player.pause()
        self.state = "idle"

    def poll(self):
        """
        Current scene frame according to the sound.

        :returns:   Fractional frame, or None when the sound isn't the clock
                    (not playing, still starting up, or finished)
        """
        if self.state not in ("starting", "running") or not self.available:
            return None

        if not self._is_playing():
            # stopped by itself: reached the end of the file
            self.state = "ended"
            return None

        position = self._player.position()

        if self.state == "starting":
            if position <= self._seek_pos:
                return None  # sound not audible yet
            self.state = "running"
            self._last_pos = position
            self._pos_clock.start()
        elif position != self._last_pos:
            self._last_pos = position
            self._pos_clock.restart()

        duration = self._player.duration()
        if duration > 0 and position >= duration - 5:
            self.state = "ended"
            return None

        # position() is only updated every so often; interpolate in between
        ms = self._last_pos + min(self._pos_clock.elapsed(), self.MAX_INTERPOLATION)
        frame = self.offset + ms / 1000.0 * self.fps

        # never go backwards when a position update lands a bit early
        if self._last_frame is not None and frame < self._last_frame:
            frame = self._last_frame
        self._last_frame = frame
        return frame

    def stop(self):
        self.state = "idle"
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass


class _FrameView(QtWidgets.QWidget):
    """Rounded black viewport that draws the current frame."""

    resized = QtCore.Signal()
    clicked = QtCore.Signal()

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)
        self._pixmap = None
        self._message = ""
        self._paused = False
        self.setMinimumSize(480, 270)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._play_icon = _make_icon("play", "#ffffff", 32)

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def set_message(self, message):
        self._message = message
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        self.update()

    def set_paused(self, paused):
        self._paused = paused
        self.update()

    def image_size(self):
        """Size available for the image, in device pixels."""
        ratio = self.devicePixelRatioF()
        return QtCore.QSize(int(self.width() * ratio), int(self.height() * ratio))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)

        rect = QtCore.QRectF(self.rect())
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(rect, 10, 10)
        painter.setClipPath(clip)
        painter.fillRect(rect, QtGui.QColor("#000000"))

        if self._pixmap is not None and not self._pixmap.isNull():
            ratio = self._pixmap.devicePixelRatio() or 1.0
            size = QtCore.QSizeF(
                self._pixmap.width() / ratio, self._pixmap.height() / ratio
            )
            size.scale(rect.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            target = QtCore.QRectF(QtCore.QPointF(0, 0), size)
            target.moveCenter(rect.center())
            painter.drawPixmap(target, self._pixmap, QtCore.QRectF(self._pixmap.rect()))

            if self._paused:
                # subtle play badge in the middle while paused
                badge = QtCore.QRectF(0, 0, 76, 76)
                badge.moveCenter(rect.center())
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(QtGui.QColor(0, 0, 0, 140))
                painter.drawEllipse(badge)
                icon_rect = QtCore.QRect(0, 0, 32, 32)
                icon_rect.moveCenter(badge.center().toPoint() + QtCore.QPoint(2, 0))
                self._play_icon.paint(painter, icon_rect)

        elif self._message:
            painter.setPen(QtGui.QColor(_TEXT_MUTED))
            painter.drawText(
                rect, QtCore.Qt.AlignmentFlag.AlignCenter, self._message
            )

        painter.end()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton and not self._message:
            self.clicked.emit()
        QtWidgets.QWidget.mouseReleaseEvent(self, event)

    def resizeEvent(self, event):
        QtWidgets.QWidget.resizeEvent(self, event)
        self.resized.emit()


class PreviewDialog(QtWidgets.QDialog):
    """
    Plays back a rendered playblast and asks whether it should be submitted.

    Use ``ask()``: returns True when the artist chose to submit, False otherwise
    (including closing the window or pressing Escape).
    """

    def __init__(
        self,
        frames_folder,
        movie_path,
        fps,
        submit_label="Submit to ShotGrid",
        submit_delay=5,
        movie_job=None,
        sound_path=None,
        sound_offset=0,
        parent=None,
    ):
        QtWidgets.QDialog.__init__(self, parent)
        self.setObjectName("PreviewDialog")

        self.movie_path = movie_path
        self.movie_job = movie_job
        self._movie_state = "pending"  # pending, ready or failed
        self._movie_error = ""
        self.submit_label = submit_label
        self.fps = float(fps) if fps else 24.0
        if self.fps <= 0:
            self.fps = 24.0

        self.frames = find_frames(frames_folder)
        self.current_index = 0
        self._submitted = False

        self._cache = collections.OrderedDict()
        self._cache_size = 10

        # Real-time playback: frame is derived from elapsed time, so slow
        # decoding drops frames instead of slowing the playback down.
        self._clock = QtCore.QElapsedTimer()
        self._base_frame = 0.0
        self._frame_numbers = [number for number, _ in self.frames]
        self._timer = QtCore.QTimer(self)
        self._timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._on_tick)

        # The submit button only becomes available after a short delay, so
        # artists actually watch the playblast before submitting it.
        self._submit_remaining = max(int(submit_delay or 0), 0)
        self._submit_timer = QtCore.QTimer(self)
        self._submit_timer.setInterval(1000)
        self._submit_timer.timeout.connect(self._on_submit_countdown)

        # scene sound (optional)
        self.audio = None
        if sound_path:
            self.audio = _AudioTrack(sound_path, sound_offset, self.fps, self)
            self.audio.failed.connect(self._on_audio_failed)

        self._icons = {
            "play": _make_icon("play", _BG),
            "pause": _make_icon("pause", _BG),
            "prev": _make_icon("prev", _TEXT),
            "next": _make_icon("next", _TEXT),
            "loop": _make_icon("loop", _TEXT),
            "sound": _make_icon("sound", _TEXT),
            "mute": _make_icon("mute", _TEXT_MUTED),
            "open": _make_icon("open", _TEXT, 16),
        }

        self.setWindowTitle("Playblast preview")
        self.setModal(True)
        self.setStyleSheet(_STYLESHEET)
        self.resize(1100, 780)

        self._build_ui()

        # Optional: the movie with slate may be rendering in the background.
        # Without a job the movie is only made after submitting, so there is
        # nothing to wait for and nothing to open yet.
        if movie_job is not None:
            movie_job.finished.connect(self._on_movie_finished)
            if movie_job.success is not None:
                self._on_movie_finished(movie_job.success, movie_job.error)
            self._update_movie_status()
        else:
            self._movie_state = "ready"
            self.status_label.hide()
            self.open_button.hide()
            self._update_submit_button()

        if self.frames:
            self._show_index(0)
            # Start playing as soon as the window is visible
            QtCore.QTimer.singleShot(0, self.play)
        else:
            self.view.set_message(
                "No preview frames found.\n"
                "Use 'Open in player' to check the movie."
            )
            self.frame_label.setText("-")
            self.frame_total_label.setText("")
            for widget in (
                self.play_button,
                self.prev_button,
                self.next_button,
                self.slider,
                self.loop_button,
            ):
                widget.setEnabled(False)

    #
    # --- UI ---
    #
    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        # --- header ---
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)

        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(2)
        title = QtWidgets.QLabel(
            os.path.basename(self.movie_path or "") or "Playblast", self
        )
        title.setObjectName("Title")
        subtitle = QtWidgets.QLabel(
            "Preview without slate"
            + ("" if self.audio is not None and self.audio.available else " and sound"),
            self,
        )
        subtitle.setObjectName("Muted")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)

        if self.frames:
            header.addWidget(
                self._chip("%d - %d" % (self.frames[0][0], self.frames[-1][0]))
            )
        header.addWidget(self._chip(("%.3f" % self.fps).rstrip("0").rstrip(".") + " fps"))

        self.open_button = QtWidgets.QPushButton("Open in player", self)
        self.open_button.setObjectName("GhostButton")
        self.open_button.setIcon(self._icons["open"])
        self.open_button.setToolTip(
            "Open the movie with slate and sound\n%s" % (self.movie_path or "")
        )
        self.open_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.open_movie)
        header.addSpacing(6)
        header.addWidget(self.open_button)
        layout.addLayout(header)

        # --- viewport ---
        self.view = _FrameView(self)
        self.view.resized.connect(self._on_view_resized)
        self.view.clicked.connect(self.toggle_play)
        layout.addWidget(self.view, 1)

        # --- transport ---
        transport = QtWidgets.QFrame(self)
        transport.setObjectName("Transport")
        controls = QtWidgets.QHBoxLayout(transport)
        controls.setContentsMargins(12, 8, 16, 8)
        controls.setSpacing(6)

        self.prev_button = self._icon_button("prev", "Previous frame  (Left)")
        self.prev_button.clicked.connect(lambda: self.step(-1))

        self.play_button = QtWidgets.QToolButton(transport)
        self.play_button.setObjectName("PlayButton")
        self.play_button.setFixedSize(36, 36)
        self.play_button.setIconSize(QtCore.QSize(18, 18))
        self.play_button.setIcon(self._icons["pause"])
        self.play_button.setToolTip("Play / pause  (Space)")
        self.play_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.play_button.clicked.connect(self.toggle_play)

        self.next_button = self._icon_button("next", "Next frame  (Right)")
        self.next_button.clicked.connect(lambda: self.step(1))

        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, transport)
        self.slider.setObjectName("Timeline")
        self.slider.setRange(0, max(len(self.frames) - 1, 0))
        self.slider.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.slider.sliderPressed.connect(self.pause)
        self.slider.valueChanged.connect(self._on_slider_changed)

        self.frame_label = QtWidgets.QLabel(transport)
        self.frame_label.setObjectName("FrameNumber")
        self.frame_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.frame_label.setMinimumWidth(48)
        self.frame_total_label = QtWidgets.QLabel(transport)
        self.frame_total_label.setObjectName("FrameTotal")
        self.frame_total_label.setMinimumWidth(64)

        self.sound_button = self._icon_button("sound", "Mute / unmute sound  (M)")
        self.sound_button.setCheckable(True)
        self.sound_button.toggled.connect(self._on_mute_toggled)
        if self.audio is None:
            self.sound_button.hide()
        elif not self.audio.available:
            self._on_audio_failed(self.audio.error)

        self.loop_button = self._icon_button("loop", "Loop playback")
        self.loop_button.setCheckable(True)
        self.loop_button.setChecked(True)

        controls.addWidget(self.prev_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.next_button)
        controls.addSpacing(8)
        controls.addWidget(self.slider, 1)
        controls.addSpacing(10)
        controls.addWidget(self.frame_label)
        controls.addWidget(self.frame_total_label)
        controls.addWidget(self.sound_button)
        controls.addWidget(self.loop_button)
        layout.addWidget(transport)

        # --- footer: question + answer ---
        footer = QtWidgets.QFrame(self)
        footer.setObjectName("Footer")
        footer_layout = QtWidgets.QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 12, 12, 12)
        footer_layout.setSpacing(10)

        question = QtWidgets.QVBoxLayout()
        question.setSpacing(2)
        question_title = QtWidgets.QLabel("Submit this playblast to ShotGrid?", self)
        question_title.setObjectName("Title")
        question_text = QtWidgets.QLabel(
            "Submitting renders the movie with slate, uploads it and creates a Version for review.",
            self,
        )
        question_text.setObjectName("Muted")
        self.status_label = QtWidgets.QLabel(self)
        self.status_label.setObjectName("Muted")
        question.addWidget(question_title)
        question.addWidget(question_text)
        question.addSpacing(4)
        question.addWidget(self.status_label)
        footer_layout.addLayout(question, 1)

        self.skip_button = QtWidgets.QPushButton("Don't submit", footer)
        self.skip_button.setObjectName("SecondaryButton")
        self.skip_button.setAutoDefault(False)
        self.skip_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.skip_button.clicked.connect(self.reject)

        self.submit_button = QtWidgets.QPushButton(self.submit_label, footer)
        self.submit_button.setObjectName("PrimaryButton")
        self.submit_button.setAutoDefault(False)
        self.submit_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.submit_button.clicked.connect(self.accept)
        self._update_submit_button()
        # keep the width stable while the button text changes
        self.submit_button.ensurePolished()
        widths = []
        for text in ("%s (%d)" % (self.submit_label, 5), "Preparing movie..."):
            self.submit_button.setText(text)
            widths.append(self.submit_button.sizeHint().width())
        self.submit_button.setMinimumWidth(max(widths))
        self.submit_button.setText(self.submit_label)

        footer_layout.addWidget(self.skip_button)
        footer_layout.addWidget(self.submit_button)
        layout.addWidget(footer)

        # Keyboard goes to the player; an accidental Enter never submits.
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        for widget in (
            self.prev_button,
            self.play_button,
            self.next_button,
            self.slider,
            self.loop_button,
            self.sound_button,
            self.open_button,
        ):
            widget.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

    def _chip(self, text):
        chip = QtWidgets.QLabel(text, self)
        chip.setObjectName("Chip")
        return chip

    def _icon_button(self, icon, tooltip):
        button = QtWidgets.QToolButton(self)
        button.setObjectName("IconButton")
        button.setIcon(self._icons[icon])
        button.setIconSize(QtCore.QSize(20, 20))
        button.setFixedSize(32, 32)
        button.setToolTip(tooltip)
        button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        return button

    #
    # --- PLAYBACK ---
    #
    # How long the picture waits for the sound to start before playing without it
    AUDIO_START_TIMEOUT = 750

    def play(self):
        if not self.frames:
            return
        if self.current_index >= len(self.frames) - 1:
            self._show_index(0)
        self._rebase(self.frames[self.current_index][0])
        self._timer.start(max(1, int(1000.0 / self.fps / 4)))
        self.play_button.setIcon(self._icons["pause"])
        self.view.set_paused(False)
        self._on_tick()

    def pause(self):
        self._timer.stop()
        if self.audio is not None:
            self.audio.pause()
        self.play_button.setIcon(self._icons["play"])
        self.view.set_paused(bool(self.frames))

    def toggle_play(self):
        if self._timer.isActive():
            self.pause()
        else:
            self.play()

    def step(self, offset):
        if not self.frames:
            return
        self.pause()
        self._show_index((self.current_index + offset) % len(self.frames))

    def _rebase(self, frame):
        """Let the internal clock continue from this scene frame."""
        self._base_frame = float(frame)
        self._clock.start()

    def _clock_frame(self):
        return self._base_frame + self._clock.elapsed() / 1000.0 * self.fps

    def _index_for_frame(self, frame):
        """Index in self.frames for a scene frame; len(frames) when past the end."""
        if frame >= self._frame_numbers[-1] + 1:
            return len(self.frames)
        return max(bisect.bisect_right(self._frame_numbers, frame + 1e-6) - 1, 0)

    def _on_tick(self):
        count = len(self.frames)
        audio = self.audio
        frame = None

        if audio is not None:
            audio_frame = audio.poll()
            if audio_frame is not None:
                # the sound is the clock
                frame = audio_frame
                self._rebase(frame)
            elif audio.state == "starting":
                if audio.start_elapsed() < self.AUDIO_START_TIMEOUT:
                    # hold the picture until the sound really plays
                    self._rebase(self._base_frame)
                    return
                # sound doesn't start: continue without it
                audio.pause()
                audio.state = "ended"

        if frame is None:
            frame = self._clock_frame()
            if (
                audio is not None
                and audio.state == "idle"
                and audio.covers(frame)
                and audio.start_at(frame)
            ):
                # entering the sound: wait for it on the next ticks
                self._rebase(frame)
                frame = self._base_frame

        index = self._index_for_frame(frame)

        if index >= count:
            if self.loop_button.isChecked():
                if audio is not None:
                    audio.pause()
                self._show_index(0)
                self._rebase(self.frames[0][0])
                self._on_tick_restart()
            else:
                if audio is not None:
                    audio.pause()
                self._show_index(count - 1)
                self.pause()
            return

        if index != self.current_index:
            self._show_index(index)

    def _on_tick_restart(self):
        """Start the sound right away after looping, if it covers the first frame."""
        audio = self.audio
        if audio is not None and audio.covers(self._base_frame):
            audio.start_at(self._base_frame)

    def _on_slider_changed(self, value):
        if value != self.current_index:
            self._show_index(value)
            if self._timer.isActive():
                if self.audio is not None:
                    self.audio.pause()
                self._rebase(self.frames[value][0])

    #
    # --- SOUND ---
    #
    def _on_mute_toggled(self, muted):
        self.sound_button.setIcon(self._icons["mute" if muted else "sound"])
        if self.audio is not None:
            self.audio.set_muted(muted)

    def _on_audio_failed(self, error):
        self.sound_button.setEnabled(False)
        self.sound_button.setIcon(self._icons["mute"])
        self.sound_button.setToolTip(error)

    def _show_index(self, index):
        self.current_index = index
        pixmap = self._get_pixmap(index)
        if pixmap is not None:
            self.view.set_pixmap(pixmap)

        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)

        self.frame_label.setText(str(self.frames[index][0]))
        self.frame_total_label.setText("  %d / %d" % (index + 1, len(self.frames)))

    def _get_pixmap(self, index):
        if index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]

        reader = QtGui.QImageReader(self.frames[index][1])
        source_size = reader.size()
        if source_size.isValid():
            scaled = source_size.scaled(
                self.view.image_size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio
            )
            # never upscale; the view scales small frames up smoothly itself
            if (
                scaled.isValid()
                and not scaled.isEmpty()
                and scaled.width() < source_size.width()
            ):
                reader.setScaledSize(scaled)

        image = reader.read()
        if image.isNull():
            return None

        pixmap = QtGui.QPixmap.fromImage(image)

        # keep the cache inside the memory budget for the current view size
        frame_bytes = max(image.width() * image.height() * 4, 1)
        self._cache_size = max(10, int(_CACHE_BUDGET / frame_bytes))
        self._cache[index] = pixmap
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

        return pixmap

    def _on_view_resized(self):
        # scaled frames are only valid for the old view size
        self._cache.clear()
        if self.frames:
            self._show_index(self.current_index)

    #
    # --- ACTIONS ---
    #
    def open_movie(self):
        """Open the rendered movie in the default video player."""
        if not self.movie_path or not os.path.isfile(self.movie_path):
            return
        self.pause()
        try:
            if sys.platform.startswith("win"):
                os.startfile(self.movie_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.movie_path])
            else:
                subprocess.Popen(["xdg-open", self.movie_path])
        except Exception as err:
            QtWidgets.QMessageBox.warning(
                self, "Open movie", "Could not open the movie:\n\n%s" % err
            )

    def keyPressEvent(self, event):
        key = event.key()
        if key == QtCore.Qt.Key.Key_Space:
            self.toggle_play()
        elif key == QtCore.Qt.Key.Key_Left:
            self.step(-1)
        elif key == QtCore.Qt.Key.Key_Right:
            self.step(1)
        elif key == QtCore.Qt.Key.Key_M:
            if self.sound_button.isVisible() and self.sound_button.isEnabled():
                self.sound_button.toggle()
        elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            # never submit by accident
            event.accept()
        else:
            QtWidgets.QDialog.keyPressEvent(self, event)

    #
    # --- SUBMIT DELAY ---
    #
    def showEvent(self, event):
        QtWidgets.QDialog.showEvent(self, event)
        # countdown starts when the window is actually on screen
        if self._submit_remaining > 0 and not self._submit_timer.isActive():
            self._submit_timer.start()

    def _on_submit_countdown(self):
        self._submit_remaining = max(self._submit_remaining - 1, 0)
        if self._submit_remaining == 0:
            self._submit_timer.stop()
        self._update_submit_button()

    #
    # --- MOVIE STATUS ---
    #
    def _on_movie_finished(self, success, error):
        self._movie_state = "ready" if success else "failed"
        self._movie_error = error or ""
        self._update_movie_status()

    def _update_movie_status(self):
        label = self.status_label
        if self._movie_state == "pending":
            label.setObjectName("Muted")
            label.setText("Rendering the movie with slate in the background...")
            label.setToolTip("")
        elif self._movie_state == "ready":
            label.setObjectName("Success")
            label.setText("Movie ready")
            label.setToolTip(self.movie_path or "")
        else:
            label.setObjectName("Error")
            first_line = (self._movie_error.splitlines() or [""])[0]
            if len(first_line) > 120:
                first_line = first_line[:117] + "..."
            label.setText("Movie failed: %s" % first_line)
            label.setToolTip(self._movie_error)
        # re-apply the stylesheet after changing the object name
        label.style().unpolish(label)
        label.style().polish(label)

        self.open_button.setEnabled(self._movie_state == "ready")
        self._update_submit_button()

    def _update_submit_button(self):
        waiting = self._submit_remaining > 0
        movie_state = getattr(self, "_movie_state", "ready")
        self.submit_button.setEnabled(not waiting and movie_state == "ready")
        if not waiting and movie_state != "ready":
            self.submit_button.setText(
                "Preparing movie..." if movie_state == "pending" else self.submit_label
            )
            self.submit_button.setToolTip(
                "Waiting for the movie with slate"
                if movie_state == "pending"
                else "The movie could not be created"
            )
            self.submit_button.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        elif waiting:
            self.submit_button.setText(
                "%s (%d)" % (self.submit_label, self._submit_remaining)
            )
            self.submit_button.setToolTip(
                "Watch the playblast first - available in %d s"
                % self._submit_remaining
            )
            self.submit_button.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        else:
            self.submit_button.setText(self.submit_label)
            self.submit_button.setToolTip("")
            self.submit_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    def accept(self):
        # safety net: never accept while the countdown is still running
        if self._submit_remaining > 0 or self._movie_state != "ready":
            return
        self._submitted = True
        QtWidgets.QDialog.accept(self)

    def done(self, result):
        self._timer.stop()
        if self.audio is not None:
            self.audio.stop()
        self._submit_timer.stop()
        self._cache.clear()
        QtWidgets.QDialog.done(self, result)

    def ask(self):
        """
        Show the dialog modally.

        :returns:   True if the artist chose to submit
        :rtype:     bool
        """
        self._submitted = False
        run = getattr(self, "exec", None) or getattr(self, "exec_")
        run()
        return self._submitted


class SavePromptDialog(QtWidgets.QDialog):
    """Asks whether a new version of the work file should be saved."""

    def __init__(self, current_path, new_path, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        # reuse the preview theme
        self.setObjectName("PreviewDialog")
        self.setStyleSheet(_STYLESHEET)
        self.setWindowTitle("Save new version")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._save = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("Save a new version of your scene?", self)
        title.setObjectName("Title")
        layout.addWidget(title)

        text = QtWidgets.QLabel(
            "Your scene will be saved as a new version, so the next playblast "
            "gets a new version number too.",
            self,
        )
        text.setObjectName("Muted")
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addSpacing(8)

        files = QtWidgets.QFrame(self)
        files.setObjectName("Footer")
        grid = QtWidgets.QGridLayout(files)
        grid.setContentsMargins(14, 10, 14, 10)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)
        for row, (name, path) in enumerate(
            (("Current", current_path), ("New", new_path))
        ):
            key = QtWidgets.QLabel(name, files)
            key.setObjectName("Muted")
            value = QtWidgets.QLabel(os.path.basename(path or "") or "-", files)
            value.setToolTip(path or "")
            value.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )
            if row == 1:
                value.setObjectName("FrameNumber")
            grid.addWidget(key, row, 0)
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(files)
        layout.addSpacing(12)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        self.skip_button = QtWidgets.QPushButton("Don't save", self)
        self.skip_button.setObjectName("SecondaryButton")
        self.skip_button.setAutoDefault(False)
        self.skip_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.skip_button.clicked.connect(self.reject)

        self.save_button = QtWidgets.QPushButton("Save new version", self)
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setDefault(True)
        self.save_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.accept)

        buttons.addWidget(self.skip_button)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)
        self.save_button.setFocus()

    def accept(self):
        self._save = True
        QtWidgets.QDialog.accept(self)

    def ask(self):
        """
        Show the dialog modally.

        :returns:   True if the artist chose to save a new version
        :rtype:     bool
        """
        self._save = False
        run = getattr(self, "exec", None) or getattr(self, "exec_")
        run()
        return self._save
