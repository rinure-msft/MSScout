from __future__ import annotations

from dataclasses import dataclass
import os
import pathlib
from typing import Protocol

import numpy as np
import sherpa_onnx

from arthur_config import get_config, get_path


MODULE_DIR = pathlib.Path(__file__).resolve().parent


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    avg_logprob: float | None = None
    no_speech_prob: float | None = None
    compression_ratio: float | None = None
    segment_count: int = 0


class SpeechTranscriber(Protocol):
    @property
    def description(self) -> str: ...

    def transcribe(
        self, audio: np.ndarray, samplerate: int
    ) -> TranscriptionResult: ...


@dataclass(frozen=True)
class ZipformerModelFiles:
    directory: pathlib.Path
    tokens: pathlib.Path
    encoder: pathlib.Path
    decoder: pathlib.Path
    joiner: pathlib.Path
    hotwords: pathlib.Path | None
    bpe_vocab: pathlib.Path | None


def _resolve_relative_path(value: str | pathlib.Path, base: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)


def resolve_model_directory(value: str | pathlib.Path | None = None) -> pathlib.Path:
    configured = value or str(
        get_config(
            "speechRecognition.modelDirectory",
            r"models\zipformer-en-balanced-int8",
        )
    )
    scratch = get_path("runtime.scratchpadPath", str(MODULE_DIR))
    return _resolve_relative_path(configured, scratch)


def _find_model_file(model_directory: pathlib.Path, pattern: str) -> pathlib.Path:
    matches = sorted(model_directory.glob(pattern))
    if not matches:
        raise FileNotFoundError(
            f"No speech model file matching {pattern!r} in {model_directory}"
        )
    return matches[0]


def sync_assistant_hotword(path: pathlib.Path) -> None:
    assistant_name = str(get_config("assistantName", "Arthur")).strip().upper()
    score = float(get_config("speechRecognition.hotwordsScore", 2.0))
    desired = f"{assistant_name} :{score:g}\n"
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""
    if current == desired:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(desired, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def resolve_zipformer_model_files(
    model_directory: str | pathlib.Path | None = None,
) -> ZipformerModelFiles:
    directory = resolve_model_directory(model_directory)
    tokens = directory / "tokens.txt"
    if not tokens.exists():
        raise FileNotFoundError(f"Speech model tokens file not found: {tokens}")

    hotwords_enabled = bool(
        get_config("speechRecognition.hotwordsEnabled", True)
    )
    hotwords = _resolve_relative_path(
        str(get_config("speechRecognition.hotwordsFile", "hotwords.txt")),
        directory,
    )
    bpe_vocab = _resolve_relative_path(
        str(get_config("speechRecognition.bpeVocab", "bpe.vocab")),
        directory,
    )
    if hotwords_enabled:
        sync_assistant_hotword(hotwords)
        if not hotwords.exists():
            raise FileNotFoundError(f"Speech hotwords file not found: {hotwords}")
        if not bpe_vocab.exists():
            raise FileNotFoundError(f"Speech BPE vocabulary not found: {bpe_vocab}")
    else:
        hotwords = None
        bpe_vocab = None

    return ZipformerModelFiles(
        directory=directory,
        tokens=tokens,
        encoder=_find_model_file(directory, "encoder*.int8.onnx"),
        decoder=_find_model_file(directory, "decoder*.int8.onnx"),
        joiner=_find_model_file(directory, "joiner*.int8.onnx"),
        hotwords=hotwords,
        bpe_vocab=bpe_vocab,
    )


class ZipformerTranscriber:
    def __init__(
        self,
        files: ZipformerModelFiles,
        num_threads: int,
        decoding_method: str,
        max_active_paths: int,
        provider: str,
        hotwords_score: float,
    ) -> None:
        if num_threads < 1:
            raise ValueError("speechRecognition.numThreads must be at least 1")
        if max_active_paths < 1:
            raise ValueError(
                "speechRecognition.maxActivePaths must be at least 1"
            )
        if decoding_method not in {"greedy_search", "modified_beam_search"}:
            raise ValueError(
                "speechRecognition.decodingMethod must be "
                "'greedy_search' or 'modified_beam_search'"
            )
        if files.hotwords and decoding_method != "modified_beam_search":
            raise ValueError(
                "Arthur hotword bias requires modified_beam_search decoding"
            )

        options: dict[str, object] = {}
        if files.hotwords and files.bpe_vocab:
            options.update(
                hotwords_file=str(files.hotwords),
                hotwords_score=hotwords_score,
                modeling_unit="bpe",
                bpe_vocab=str(files.bpe_vocab),
            )

        self.files = files
        self.num_threads = num_threads
        self.decoding_method = decoding_method
        self.max_active_paths = max_active_paths
        self.provider = provider
        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(files.tokens),
            encoder=str(files.encoder),
            decoder=str(files.decoder),
            joiner=str(files.joiner),
            num_threads=num_threads,
            decoding_method=decoding_method,
            max_active_paths=max_active_paths,
            provider=provider,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.4,
            rule2_min_trailing_silence=0.8,
            rule3_min_utterance_length=20.0,
            **options,
        )

    @property
    def description(self) -> str:
        hotwords = "enabled" if self.files.hotwords else "disabled"
        return (
            f"Zipformer INT8 at {self.files.directory}; "
            f"threads={self.num_threads}; decoding={self.decoding_method}; "
            f"hotwords={hotwords}"
        )

    def transcribe(
        self, audio: np.ndarray, samplerate: int
    ) -> TranscriptionResult:
        if audio.size == 0:
            return TranscriptionResult(text="")

        samples = np.asarray(audio).reshape(-1)
        if np.issubdtype(samples.dtype, np.integer):
            info = np.iinfo(samples.dtype)
            scale = float(max(abs(info.min), info.max))
            samples = samples.astype(np.float32) / scale
        else:
            samples = samples.astype(np.float32)

        stream = self.recognizer.create_stream()
        stream.accept_waveform(samplerate, samples)
        stream.input_finished()
        while self.recognizer.is_ready(stream):
            self.recognizer.decode_stream(stream)

        text = " ".join(self.recognizer.get_result(stream).split()).rstrip(" .")
        return TranscriptionResult(
            text=text,
            segment_count=1 if text else 0,
        )


def inspect_backend(
    backend: str | None = None,
) -> str:
    selected_backend = (
        backend
        or str(get_config("speechRecognition.backend", "zipformer"))
    ).strip().lower()
    if selected_backend != "zipformer":
        raise ValueError("speechRecognition.backend must be 'zipformer'")
    files = resolve_zipformer_model_files()
    return f"Zipformer INT8 model files ready at {files.directory}"


def prepare_backend(
    backend: str | None = None,
) -> str:
    selected_backend = (
        backend
        or str(get_config("speechRecognition.backend", "zipformer"))
    ).strip().lower()
    if selected_backend != "zipformer":
        raise ValueError("speechRecognition.backend must be 'zipformer'")
    return inspect_backend("zipformer")


def build_transcriber(
    *,
    backend: str | None = None,
    model_directory: str | pathlib.Path | None = None,
    num_threads: int | None = None,
    decoding_method: str | None = None,
) -> SpeechTranscriber:
    selected_backend = (
        backend
        or str(get_config("speechRecognition.backend", "zipformer"))
    ).strip().lower()
    if selected_backend != "zipformer":
        raise ValueError("speechRecognition.backend must be 'zipformer'")

    configured_threads = int(
        get_config(
            "speechRecognition.numThreads",
            max(1, min(4, os.cpu_count() or 1)),
        )
    )
    files = resolve_zipformer_model_files(model_directory)
    return ZipformerTranscriber(
        files=files,
        num_threads=(
            configured_threads if num_threads is None else num_threads
        ),
        decoding_method=decoding_method
        or str(
            get_config(
                "speechRecognition.decodingMethod",
                "modified_beam_search",
            )
        ),
        max_active_paths=int(
            get_config("speechRecognition.maxActivePaths", 4)
        ),
        provider=str(get_config("speechRecognition.provider", "cpu")),
        hotwords_score=float(
            get_config("speechRecognition.hotwordsScore", 2.0)
        ),
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Prepare or inspect Arthur speech recognition."
    )
    parser.add_argument(
        "--backend",
        choices=("zipformer",),
    )
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    message = (
        prepare_backend(args.backend)
        if args.prepare
        else inspect_backend(args.backend)
    )
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
