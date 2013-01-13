"""Bindings for FFmpegSource
"""
#   © 2012 spirit <hiddenspirit@gmail.com>
#   https://bitbucket.org/spirit/ffms
#
#   This program is free software: you can redistribute it and/or modify it
#   under the terms of the GNU Lesser General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#   See the GNU Lesser General Public License for more details.
#
#   You should have received a copy of the GNU Lesser General Public License
#   along with this program. If not, see <http://www.gnu.org/licenses/>.

import contextlib
import functools
import math
import os
import sys
import time

from collections import namedtuple
from fractions import Fraction

try:
    from collections.abc import Iterable, Sized
except ImportError:
    from collections import Iterable, Sized

try:
    from multiprocessing import cpu_count
except (ImportError, NotImplementedError):
    cpu_count = None

from ctypes import *

# TODO: Use stdlib if numpy is not available.
import numpy

from .libffms2 import *
from .enums import *
from .av_log import *


__all__ = [
    "get_version", "get_pix_fmt", "get_present_sources", "get_enabled_sources",
    "get_log_level", "set_log_level", "Error", "Indexer", "Index",
    "VideoSource", "AudioSource",
    "FFINDEX_EXT", "DEFAULT_AUDIO_FILENAME_FORMAT",

    "FFMS_CH_BACK_CENTER", "FFMS_CH_BACK_LEFT", "FFMS_CH_BACK_RIGHT",
    "FFMS_CH_FRONT_CENTER", "FFMS_CH_FRONT_LEFT",
    "FFMS_CH_FRONT_LEFT_OF_CENTER", "FFMS_CH_FRONT_RIGHT",
    "FFMS_CH_FRONT_RIGHT_OF_CENTER", "FFMS_CH_LOW_FREQUENCY",
    "FFMS_CH_SIDE_LEFT", "FFMS_CH_SIDE_RIGHT", "FFMS_CH_STEREO_LEFT",
    "FFMS_CH_STEREO_RIGHT", "FFMS_CH_TOP_BACK_CENTER", "FFMS_CH_TOP_BACK_LEFT",
    "FFMS_CH_TOP_BACK_RIGHT", "FFMS_CH_TOP_CENTER", "FFMS_CH_TOP_FRONT_CENTER",
    "FFMS_CH_TOP_FRONT_LEFT", "FFMS_CH_TOP_FRONT_RIGHT", "FFMS_CPU_CAPS_3DNOW",
    "FFMS_CPU_CAPS_ALTIVEC", "FFMS_CPU_CAPS_BFIN", "FFMS_CPU_CAPS_MMX",
    "FFMS_CPU_CAPS_MMX2", "FFMS_CPU_CAPS_SSE2", "FFMS_CR_JPEG", "FFMS_CR_MPEG",
    "FFMS_CR_UNSPECIFIED", "FFMS_CS_BT470BG", "FFMS_CS_BT709", "FFMS_CS_FCC",
    "FFMS_CS_RGB", "FFMS_CS_SMPTE170M", "FFMS_CS_SMPTE240M",
    "FFMS_CS_UNSPECIFIED", "FFMS_DELAY_FIRST_VIDEO_TRACK",
    "FFMS_DELAY_NO_SHIFT", "FFMS_DELAY_TIME_ZERO",
    "FFMS_ERROR_ALLOCATION_FAILED", "FFMS_ERROR_CANCELLED", "FFMS_ERROR_CODEC",
    "FFMS_ERROR_DECODING", "FFMS_ERROR_FILE_MISMATCH", "FFMS_ERROR_FILE_READ",
    "FFMS_ERROR_FILE_WRITE", "FFMS_ERROR_INDEX", "FFMS_ERROR_INDEXING",
    "FFMS_ERROR_INVALID_ARGUMENT", "FFMS_ERROR_NOT_AVAILABLE",
    "FFMS_ERROR_NO_FILE", "FFMS_ERROR_PARSER", "FFMS_ERROR_POSTPROCESSING",
    "FFMS_ERROR_SCALING", "FFMS_ERROR_SEEKING", "FFMS_ERROR_SUCCESS",
    "FFMS_ERROR_TRACK", "FFMS_ERROR_UNKNOWN", "FFMS_ERROR_UNSUPPORTED",
    "FFMS_ERROR_USER", "FFMS_ERROR_VERSION", "FFMS_ERROR_WAVE_WRITER",
    "FFMS_FMT_DBL", "FFMS_FMT_FLT", "FFMS_FMT_S16", "FFMS_FMT_S32",
    "FFMS_FMT_U8", "FFMS_IEH_ABORT", "FFMS_IEH_CLEAR_TRACK", "FFMS_IEH_IGNORE",
    "FFMS_IEH_STOP_TRACK", "FFMS_RESIZER_AREA", "FFMS_RESIZER_BICUBIC",
    "FFMS_RESIZER_BICUBLIN", "FFMS_RESIZER_BILINEAR",
    "FFMS_RESIZER_FAST_BILINEAR", "FFMS_RESIZER_GAUSS", "FFMS_RESIZER_LANCZOS",
    "FFMS_RESIZER_POINT", "FFMS_RESIZER_SINC", "FFMS_RESIZER_SPLINE",
    "FFMS_RESIZER_X", "FFMS_SEEK_AGGRESSIVE", "FFMS_SEEK_LINEAR",
    "FFMS_SEEK_LINEAR_NO_RW", "FFMS_SEEK_NORMAL", "FFMS_SEEK_UNSAFE",
    "FFMS_SOURCE_DEFAULT", "FFMS_SOURCE_HAALIMPEG", "FFMS_SOURCE_HAALIOGG",
    "FFMS_SOURCE_LAVF", "FFMS_SOURCE_MATROSKA", "FFMS_TYPE_ATTACHMENT",
    "FFMS_TYPE_AUDIO", "FFMS_TYPE_DATA", "FFMS_TYPE_SUBTITLE",
    "FFMS_TYPE_UNKNOWN", "FFMS_TYPE_VIDEO",

    "AV_LOG_QUIET", "AV_LOG_PANIC", "AV_LOG_FATAL", "AV_LOG_ERROR",
    "AV_LOG_WARNING", "AV_LOG_INFO", "AV_LOG_VERBOSE", "AV_LOG_DEBUG",
]

FFINDEX_EXT = ".ffindex"
DEFAULT_AUDIO_FILENAME_FORMAT = "%sourcefile%_track%trackzn%.w64"
PIX_FMT_NONE = FFMS_GetPixFmt(b"none")


if os.name == "nt":
    import atexit
    import pythoncom #@UnresolvedImport

    # http://code.google.com/p/ffmpegsource/issues/detail?id=58
    USE_UTF8_PATHS = True

    if USE_UTF8_PATHS:
        FILENAME_ENCODING = "utf-8"

        def get_encoded_path(path):
            return path.encode(FILENAME_ENCODING)
    else:
        import win32api #@UnresolvedImport

        FILENAME_ENCODING = sys.getfilesystemencoding()

        def get_encoded_path(path):
            if not os.path.exists(path):
                with open(path, "w"):
                    pass
            return win32api.GetShortPathName(path).encode(FILENAME_ENCODING)

    def ffms_init():
        if not getattr(pythoncom, "_initialized", False):
            try:
                pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
            except pythoncom.error:
                pass
            else:
                pythoncom._initialized = True
                atexit.register(ffms_uninit)
        FFMS_Init(0, USE_UTF8_PATHS)

    def ffms_uninit():
        pythoncom.CoUninitialize()
        pythoncom._initialized = False

    ffms_init()
else:
    FILENAME_ENCODING = sys.getfilesystemencoding()

    def get_encoded_path(path):
        return path.encode(FILENAME_ENCODING)

    FFMS_Init(0, 0)


if FFMS_SetOutputFormatV2 is None:
    def FFMS_SetOutputFormatV2(source, target_formats, width, height, resizer,
                               p_err_info):
        """Substitute when using FFMS 2.15-
        """
        while target_formats and target_formats[-1] < 0:
            target_formats = target_formats[:-1]
        return FFMS_SetOutputFormatV(source, list_to_mask(target_formats),
                                     width, height, resizer, p_err_info)


def get_version_info():
    """Return library FFMS_VERSION as a tuple.
    """
    VersionInfo = namedtuple("VersionInfo",
                             ("major", "minor", "micro", "bump"))
    n = FFMS_GetVersion()
    major, r = divmod(n, 1 << 24)
    minor, r = divmod(r, 1 << 16)
    micro, bump = divmod(r, 1 << 8)
    return VersionInfo(major, minor, micro, bump)


def get_version():
    """Return library FFMS_VERSION as a string.
    """
    version_info = get_version_info()
    for n, e in enumerate(reversed(version_info[1:])):
        if e:
            break
    return ".".join(str(e) for e in version_info[:len(version_info) - n])


def get_pix_fmt(name):
    """Get a colorspace identifier from a colorspace name.
    """
    return FFMS_GetPixFmt(name.encode())


def get_present_sources():
    """Check what source modules the library was compiled with.
    """
    return FFMS_GetPresentSources()


def get_enabled_sources():
    """Check what source modules are actually available for use.
    """
    return FFMS_GetEnabledSources()


def get_log_level():
    """Get FFmpeg message level.
    """
    return FFMS_GetLogLevel()


def set_log_level(level=AV_LOG_QUIET):
    """Set FFmpeg message level.
    """
    return FFMS_SetLogLevel(level)


err_msg = create_string_buffer(1024)
err_info = FFMS_ErrorInfo(FFMS_ERROR_SUCCESS, FFMS_ERROR_SUCCESS,
                          sizeof(err_msg), cast(err_msg, STRING))


class Error(Exception):
    """FFMS_ErrorInfo
    """
    def __init__(self, msg="",
                 error_type=FFMS_ERROR_SUCCESS, sub_type=FFMS_ERROR_SUCCESS):
        if msg:
            super().__init__(msg)
            self.error_type = error_type
            self.sub_type = sub_type
        else:
            super().__init__(err_info.Buffer.decode())
            self.error_type = err_info.ErrorType
            self.sub_type = err_info.SubType


class Indexer:
    """FFMS_Indexer
    """
    _AUDIO_DUMP_EXT = ".w64"

    def __init__(self, source_file, demuxer=FFMS_SOURCE_DEFAULT):
        """Create an indexer object for the given source file.
        """
        self._FFMS_CancelIndexing = FFMS_CancelIndexing
        self._indexer = FFMS_CreateIndexerWithDemuxer(
            get_encoded_path(source_file), demuxer, byref(err_info))
        if not self._indexer:
            raise Error
        self.source_file = source_file
        self._track_info_list = None

    def __del__(self):
        if self._indexer:
            self._FFMS_CancelIndexing(self._indexer)

    @property
    def track_info_list(self):
        """List of track information
        """
        self._check_indexer()
        if self._track_info_list is None:
            TrackInfo = namedtuple("TrackInfo", ("type", "codec_name"))
            self._track_info_list = []
            for n in range(FFMS_GetNumTracksI(self._indexer)):
                codec_name = FFMS_GetCodecNameI(self._indexer, n)
                if isinstance(codec_name, bytes):
                    codec_name = codec_name.decode()
                info = TrackInfo(FFMS_GetTrackTypeI(self._indexer, n),
                                 codec_name)
                self._track_info_list.append(info)
        return self._track_info_list

    @property
    def format_name(self):
        """Name of the container format
        """
        self._check_indexer()
        format_name = FFMS_GetFormatNameI(self._indexer)
        if isinstance(format_name, bytes):
            format_name = format_name.decode()
        return format_name

    @property
    def source_type(self):
        """Source module that was used to open the indexer
        """
        self._check_indexer()
        return FFMS_GetSourceTypeI(self._indexer)

    def do_indexing(self, index_mask=0, dump_mask=0,
                    anc=FFMS_DefaultAudioFilename,
                    anc_private=DEFAULT_AUDIO_FILENAME_FORMAT,
                    error_handling=FFMS_IEH_STOP_TRACK,
                    ic=None, ic_private=None):
        """Index the file.
        """
        self._check_indexer()
        if isinstance(index_mask, Iterable):
            index_mask = list_to_mask(index_mask)
        if isinstance(dump_mask, Iterable):
            dump_mask = list_to_mask(dump_mask)
        if anc is FFMS_DefaultAudioFilename and isinstance(anc_private, str):
            if not anc_private.lower().endswith(self._AUDIO_DUMP_EXT):
                anc_private += self._AUDIO_DUMP_EXT
            anc_private = anc_private.encode(FILENAME_ENCODING)
        anc = TAudioNameCallback(anc) if anc else cast(anc, TAudioNameCallback)
        ic = TIndexCallback(ic) if ic else cast(ic, TIndexCallback)
        index = FFMS_DoIndexing(self._indexer, index_mask, dump_mask,
                                anc, cast(anc_private, c_void_p),
                                error_handling,
                                ic, cast(ic_private, c_void_p),
                                byref(err_info))
        self._indexer = None
        if not index:
            raise Error
        return Index(index, source_file=self.source_file)

    def _check_indexer(self):
        if not self._indexer:
            raise ValueError("indexing already done")


class Index:
    """FFMS_Index
    """
    def __init__(self, index, index_file=None, source_file=None):
        self._FFMS_DestroyIndex = FFMS_DestroyIndex
        self._index = index
        self.index_file = index_file
        self.source_file = source_file
        self._tracks = None

    @classmethod
    def make(cls, source_file, index_mask=0, dump_mask=0,
             anc=FFMS_DefaultAudioFilename,
             anc_private=DEFAULT_AUDIO_FILENAME_FORMAT,
             error_handling=FFMS_IEH_STOP_TRACK,
             ic=None, ic_private=None):
        """Index a given source file.
        """
        return Indexer(source_file).do_indexing(
            index_mask, dump_mask, anc, anc_private, error_handling,
            ic, ic_private)

    @classmethod
    def read(cls, index_file=None, source_file=None):
        """Read an index file from disk.
        """
        if not index_file:
            if not source_file:
                raise ValueError(
                    "must provide either index file or source file")
            index_file = source_file + FFINDEX_EXT
        # FFMS_ReadIndex() under Windows will hang if index file doesn’t exist.
        # Tested with FFMS 2.17
        if not os.path.isfile(index_file):
            raise Error("no index file {!r}".format(index_file),
                        FFMS_ERROR_PARSER, FFMS_ERROR_FILE_READ)
        elif os.path.getsize(index_file) < 76:
            raise Error("bad index file {!r}".format(index_file),
                        FFMS_ERROR_PARSER, FFMS_ERROR_FILE_READ)
        index = FFMS_ReadIndex(get_encoded_path(index_file), byref(err_info))
        if not index:
            raise Error
        self = cls(index, index_file, source_file)
        if source_file and not self.belongs_to_file(source_file):
            raise Error
        return self

    def __del__(self):
        self._FFMS_DestroyIndex(self._index)

    def write(self, index_file=None):
        """Write an index object to disk.
        """
        if index_file:
            self.index_file = index_file
        elif not self.index_file:
            self.index_file = self.source_file + FFINDEX_EXT
        if FFMS_WriteIndex(get_encoded_path(self.index_file),
                           self._index, byref(err_info)):
            raise Error

    @property
    def source_type(self):
        """Source module that was used to open the index.
        """
        return FFMS_GetSourceType(self._index)

    @property
    def error_handling(self):
        """Error handling mode that was used when creating the index.
        """
        return FFMS_GetErrorHandling(self._index)

    def get_first_track_of_type(self, track_type=FFMS_TYPE_VIDEO):
        """Get the track number of the first track of a given type.
        """
        track_number = FFMS_GetFirstTrackOfType(self._index, track_type,
                                                byref(err_info))
        if track_number < 0:
            raise Error
        return track_number

    def get_first_indexed_track_of_type(self, track_type=FFMS_TYPE_VIDEO):
        """Get the track number of the first indexed track of a given type.
        """
        track_number = FFMS_GetFirstIndexedTrackOfType(self._index, track_type,
                                                       byref(err_info))
        if track_number < 0:
            raise Error
        return track_number

    @property
    def tracks(self):
        """List of tracks
        """
        if self._tracks is None:
            self._tracks = []
            for n in range(FFMS_GetNumTracks(self._index)):
                track = Track.create(FFMS_GetTrackFromIndex(self._index, n),
                                     n, self)
                self._tracks.append(track)
        return self._tracks

    def belongs_to_file(self, source_file):
        """Check whether the index belongs to a given file.
        """
        return FFMS_IndexBelongsToFile(
            self._index, get_encoded_path(source_file), byref(err_info)) == 0


class VideoType:
    type = FFMS_TYPE_VIDEO #@ReservedAssignment


class AudioType:
    type = FFMS_TYPE_AUDIO #@ReservedAssignment


class Source:
    def __init__(self, source_file, track_number=None, index=None):
        if not index:
            try:
                index = Index.read(source_file=source_file)
            except Error:
                indexer = Indexer(source_file)
                if track_number is None:
                    for track_number, i in enumerate(indexer.track_info_list):
                        if i.type == self.type:
                            break
                    else:
                        raise Error("no suitable track",
                                    FFMS_ERROR_INDEX, FFMS_ERROR_NOT_AVAILABLE)
                index = indexer.do_indexing([track_number])
        self.track_number = (
            track_number if track_number is not None
            else index.get_first_indexed_track_of_type(self.type)
        )
        self.index = index
        self._track = None


class VideoSource(VideoType, Source):
    """FFMS_VideoSource
    """
    _MAX_THREADS = min(cpu_count(), 8) if cpu_count is not None else 1

    def __init__(self, source_file, track_number=None, index=None,
                 num_threads=None, seek_mode=FFMS_SEEK_NORMAL):
        """Create a video source object.
        """
        self._FFMS_DestroyVideoSource = FFMS_DestroyVideoSource
        super().__init__(source_file, track_number, index)
        self.num_threads = (num_threads if num_threads is not None
                            else self._MAX_THREADS)
        self._source = FFMS_CreateVideoSource(
            get_encoded_path(self.index.source_file), self.track_number,
            self.index._index, self.num_threads, seek_mode, byref(err_info))
        if not self._source:
            raise Error
        self.properties = FFMS_GetVideoProperties(self._source)[0]

    def __del__(self):
        self._FFMS_DestroyVideoSource(self._source)

    def get_frame(self, n):
        """Retrieve a given video frame.
        """
        frame = FFMS_GetFrame(self._source, n, byref(err_info))
        if not frame:
            # HACK: Seems like it can fail sometimes. Fixed by retrying…
            frame = FFMS_GetFrame(self._source, n, byref(err_info))
            if not frame:
                raise Error
        return frame[0]

    def get_frame_by_time(self, time):
        """Retrieve a video frame at a given timestamp.
        (Closest frame from PTS)
        """
        frame = FFMS_GetFrameByTime(self._source, time, byref(err_info))
        if not frame:
            frame = FFMS_GetFrameByTime(self._source, time, byref(err_info))
            if not frame:
                raise Error
        return frame[0]

    def set_output_format(self, target_formats=None, width=None, height=None,
                          resizer=FFMS_RESIZER_BICUBIC):
        """Set the output format for video frames.
        """
        frame = self.get_frame(0)
        if target_formats is None:
            target_formats = [frame.ConvertedPixelFormat
                              if frame.ConvertedPixelFormat > 0
                              else frame.EncodedPixelFormat]
        elif isinstance(target_formats, int):
            target_formats = mask_to_list(target_formats)
        if target_formats[-1] >= 0:
            target_formats.append(-1)
        if width is None:
            width = (frame.ScaledWidth
                     if frame.ScaledWidth > 0
                     else frame.EncodedWidth)
        if height is None:
            height = (frame.ScaledHeight
                      if frame.ScaledHeight > 0
                      else frame.EncodedHeight)
        r = FFMS_SetOutputFormatV2(
            self._source,
            cast((c_int * len(target_formats))(*target_formats),
                 POINTER(c_int)),
            width, height, resizer, byref(err_info)
        )
        if r:
            raise Error

    def reset_output_format(self):
        """Reset the video output format.
        """
        FFMS_ResetOutputFormatV(self._source)

    @contextlib.contextmanager
    def output_format(self, target_formats=None, width=None, height=None,
                      resizer=FFMS_RESIZER_BICUBIC):
        """Context manager to set the video output format
        """
        self.set_output_format(target_formats, width, height, resizer)
        yield
        self.reset_output_format()

    def set_input_format(self, color_space=FFMS_CS_UNSPECIFIED,
                         color_range=FFMS_CR_UNSPECIFIED,
                         pixel_format=PIX_FMT_NONE):
        """Override the source format for video frames.
        """
        r = FFMS_SetInputFormatV(self._source, color_space, color_range,
                                 pixel_format, byref(err_info))
        if r:
            raise Error

    def reset_input_format(self):
        """Reset the video input format.
        """
        FFMS_ResetInputFormatV(self._source)

    @contextlib.contextmanager
    def input_format(self, color_space=FFMS_CS_UNSPECIFIED,
                     color_range=FFMS_CR_UNSPECIFIED, pixel_format=-1):
        """Context manager to override the source format
        """
        self.set_input_format(color_space, color_range, pixel_format)
        yield
        self.reset_input_format()

    @property
    def track(self):
        """Track from video source
        """
        if self._track is None:
            self._track = VideoTrack(FFMS_GetTrackFromVideo(self._source),
                                     self.track_number, self.index)
        return self._track


def _get_planes(frame):
    height = (frame.ScaledHeight if frame.ScaledHeight > 0
              else frame.EncodedHeight)
    return [
        numpy.frombuffer(
            cast(
                frame.Data[n],
                POINTER(frame.Linesize[n] * height * c_uint8)
            )[0],
            numpy.uint8
        ) if frame.Linesize[n] else numpy.empty((0,), numpy.uint8)
        for n in range(len(frame.Data))
    ]

FFMS_Frame.planes = property(_get_planes)


def _get_fps(properties):
    return Fraction(properties.FPSNumerator, properties.FPSDenominator)


def _get_rff(properties):
    return Fraction(properties.RFFNumerator, properties.RFFDenominator)


def _get_sar(properties):
    return Fraction(properties.SARNum, properties.SARDen)

FFMS_VideoProperties.fps = property(_get_fps)
FFMS_VideoProperties.rff = property(_get_rff)
FFMS_VideoProperties.sar = property(_get_sar)


class AudioSource(AudioType, Source):
    """FFMS_AudioSource
    """
    _DEFAULT_RATE = 100
    _SAMPLE_TYPES = [
        numpy.uint8,
        numpy.int16,
        numpy.int32,
        numpy.float32,
        numpy.float64,
    ]

    def __init__(self, source_file, track_number=None, index=None,
                 delay_mode=FFMS_DELAY_FIRST_VIDEO_TRACK):
        """Create an audio source object.
        """
        self._FFMS_DestroyAudioSource = FFMS_DestroyAudioSource
        super().__init__(source_file, track_number, index)
        self._source = FFMS_CreateAudioSource(
            get_encoded_path(self.index.source_file), self.track_number,
            self.index._index, delay_mode, byref(err_info))
        if not self._source:
            raise Error
        self.properties = FFMS_GetAudioProperties(self._source)[0]
        self.sample_type = self._SAMPLE_TYPES[self.properties.SampleFormat]

    def __del__(self):
        self._FFMS_DestroyAudioSource(self._source)

    def init_buffer(self, count=1):
        """Initialize the buffer for get_audio().
        """
        self.count = count
        self.audio = numpy.empty((count, self.properties.Channels),
                                 self.sample_type)
        self.buf = self.audio.ctypes.data_as(c_void_p)

    def get_audio(self, start):
        """Decode a number of audio samples.
        """
        # FFMS 2.17: ReadPacket error or even core dump
        # for random accesses under Linux?
        if FFMS_GetAudio(self._source, self.buf,
                         start, self.count, byref(err_info)):
            raise Error
        return self.audio

    def linear_access(self, start=0, end=None, rate=_DEFAULT_RATE):
        """Return a linear iterator over the audio samples.
        """
        return AudioLinearAccess(self, start, end, rate)

    @property
    def track(self):
        """Track from audio source
        """
        if self._track is None:
            self._track = AudioTrack(FFMS_GetTrackFromAudio(self._source),
                                     self.track_number, self.index)
        return self._track


class AudioLinearAccess(Sized, Iterable):
    """Linear access to audio
    """
    def __init__(self, parent, start_frame=0, end_frame=None,
                 rate=AudioSource._DEFAULT_RATE):
        self.parent = parent
        self.num_samples = parent.properties.NumSamples
        self.start_frame = (self.num_samples + start_frame
                            if start_frame < 0 else start_frame)
        self.end_frame = (self.num_samples if end_frame is None
                          else self.num_samples + end_frame if end_frame < 0
                          else end_frame)
        sample_rate = parent.properties.SampleRate
        self.count_l, mod = divmod(sample_rate, rate)
        if not mod:
            self.samples_per_frame = self.count_h = self.count_l
            self.l = self.h = rate // 2
        else:
            self.samples_per_frame = sample_rate / rate
            self.count_h = self.count_l + 1
            self.l = self.count_h * rate - sample_rate
            self.h = rate - self.l

    def __len__(self):
        return math.ceil(self.num_samples / self.samples_per_frame)

    def __iter__(self):
        source = self.parent._source
        l, count_l = self.l, self.count_l
        h, count_h = self.h, self.count_h
        audio_l = numpy.empty((count_l, self.parent.properties.Channels),
                              self.parent.sample_type)
        buf_l = audio_l.ctypes.data_as(c_void_p)
        audio_h = numpy.empty((count_h, self.parent.properties.Channels),
                              self.parent.sample_type)
        buf_h = audio_h.ctypes.data_as(c_void_p)
        p = self.start_frame
        end = self.end_frame
        loop = True
        while loop:
            for n_range, count, audio, buf in [(h, count_h, audio_h, buf_h),
                                               (l, count_l, audio_l, buf_l)]:
                for _ in range(n_range):
                    np = p + count
                    if np > end:
                        loop = False
                        break
                    if FFMS_GetAudio(source, buf, p, count, byref(err_info)):
                        raise Error
                    p = np
                    yield audio
        count = end - p
        if count:
            audio = numpy.empty((count, self.parent.properties.Channels),
                                self.parent.sample_type)
            buf = audio.ctypes.data_as(c_void_p)
            if FFMS_GetAudio(source, buf, p, count, byref(err_info)):
                raise Error
            yield audio


class Track:
    """FFMS_Track
    """
    def __init__(self, track, number, index):
        self._track = track
        self.number = number
        self.index = index
        self._frame_info_list = None

    @classmethod
    def create(cls, track, number, index):
        t = FFMS_GetTrackType(track)
        for c in cls.__subclasses__():
            if c.type == t:
                cls = c
                break
        return cls(track, number, index)

    @property
    def type(self): #@ReservedAssignment
        """Track type
        """
        return FFMS_GetTrackType(self._track)

    @property
    def frame_info_list(self):
        """List of frame information
        """
        if self._frame_info_list is None:
            self._frame_info_list = [
                FFMS_GetFrameInfo(self._track, n)[0]
                for n in range(FFMS_GetNumFrames(self._track))
            ]
        return self._frame_info_list

    def _get_output_file(self, ext):
        index_file = (self.index.index_file or
                      self.index.source_file + FFINDEX_EXT)
        return "{}_track{:02}.{}.txt".format(index_file, self.number, ext)


class VideoTrack(VideoType, Track):
    """FFMS_Track of type FFMS_TYPE_VIDEO
    """
    _KEYFRAME_FORMAT_VERSION = 1

    def __init__(self, track, number, index):
        super().__init__(track, number, index)
        self._timecodes = None

    @property
    def time_base(self):
        """Time base
        """
        time_base = FFMS_GetTimeBase(self._track)[0]
        return Fraction(time_base.Num, time_base.Den)

    @property
    def timecodes(self):
        """List of timecodes
        """
        if self._timecodes is None:
            num, den = self.time_base.numerator, self.time_base.denominator
            self._timecodes = [frame_info.PTS * num / den
                               for frame_info in self.frame_info_list]
        return self._timecodes

    def write_timecodes(self, timecodes_file=None):
        """Write timecodes to disk.
        """
        if not timecodes_file:
            timecodes_file = self._get_output_file("tc")
        if FFMS_WriteTimecodes(self._track, get_encoded_path(timecodes_file),
                               byref(err_info)):
            raise Error

    @property
    def keyframes(self):
        """List of keyframe positions
        """
        return [n for n in range(len(self.frame_info_list))
                if self.frame_info_list[n].KeyFrame]

    @property
    def keyframes_as_timecodes(self):
        """List of keyframes as timecodes
        """
        return [self.timecodes[n] for n in self.keyframes]

    def write_keyframes(self, keyframes_file=None):
        """Write keyframe numbers to disk.
        """
        if not keyframes_file:
            keyframes_file = self._get_output_file("kf")
        if self._KEYFRAME_FORMAT_VERSION == 1:
            with open(keyframes_file, "w") as f:
                f.write("# keyframe format v{}\n"
                        .format(self._KEYFRAME_FORMAT_VERSION))
                # Though keyframe format v1 has an FPS line,
                # we can’t rely on it to properly calculate timecodes.
                if self.index.source_file:
                    vsource = VideoSource(self.index.source_file, self.number,
                                          self.index)
                    vprops = vsource.properties
                    fps = vprops.FPSNumerator / vprops.FPSDenominator
                else:
                    fps = 0
                f.write("fps {:f}\n".format(fps))
                f.writelines(["{:d}\n".format(n) for n in self.keyframes])
        else:
            raise ValueError("unsupported keyframe format version: {}"
                             .format(self._KEYFRAME_FORMAT_VERSION))


class AudioTrack(AudioType, Track):
    """FFMS_Track of type FFMS_TYPE_AUDIO
    """


def list_to_mask(l):
    return functools.reduce(lambda a, b: a | 1 << b, l, 0)


def mask_to_list(m, num_bits=64):
    return [n for n in range(num_bits) if m & 1 << n]


def init_progress_callback(msg="Indexing…", time_threshold=1, check_time=0.2):
    """Initialize and return a progress callback for the text terminal.
    """
    def ic(current, total, private=None):
        pct = current * 100 // total
        if ic.show_pct:
            if pct > ic.pct:
                ic.pct = pct
                sys.stdout.write("\r{} {:d}%".format(msg, pct))
                sys.stdout.flush()
        elif time.time() - start_time >= check_time and pct < pct_threshold:
            ic.show_pct = True
        return 0

    def done():
        ic(1, 1)
        print()

    sys.stdout.write(msg)
    sys.stdout.flush()
    ic.done = done
    ic.pct = -1
    ic.show_pct = False
    pct_threshold = int(check_time * 100 / time_threshold)
    start_time = time.time()
    return ic
