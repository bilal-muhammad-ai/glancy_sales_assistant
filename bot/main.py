"""Pipecat voice bot: Deepgram STT/TTS, Groq LLM, Chroma RAG tool."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Ensure project root is on sys.path when run as a script.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=True)

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    ErrorFrame,
    Frame,
    FunctionCallResultFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMRunFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

from bot.context_trim import ContextTrimProcessor
from bot.debug_log import dbg
from bot.prompts import VOICE_SYSTEM_PROMPT
from bot.tools.search_kb import search_site_kb
from kb.settings import get_settings


# #region agent log
class DebugProbeProcessor(FrameProcessor):
    """Log key LLM/tool/error frames without changing pipeline behavior."""

    def __init__(self, name: str, **kwargs):
        super().__init__(**kwargs)
        self._probe = name

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, ErrorFrame):
            err = getattr(frame, "error", None) or str(frame)
            dbg(
                "A",
                f"main.py:{self._probe}",
                "error_frame",
                {
                    "direction": str(direction),
                    "error": str(err)[:500],
                    "fatal": bool(getattr(frame, "fatal", False)),
                    "runId": "post-fix",
                },
            )
        elif isinstance(frame, TranscriptionFrame):
            text = getattr(frame, "text", "") or ""
            dbg(
                "F",
                f"main.py:{self._probe}",
                "transcription",
                {
                    "direction": str(direction),
                    "chars": len(text),
                    "preview": text[:120],
                    "runId": "post-fix",
                },
            )
        elif isinstance(frame, LLMContextFrame):
            msgs = frame.context.get_messages() if getattr(frame, "context", None) else []
            roles = [
                (m.get("role") if isinstance(m, dict) else type(m).__name__) for m in msgs
            ]
            dbg(
                "C",
                f"main.py:{self._probe}",
                "llm_context_frame",
                {
                    "direction": str(direction),
                    "n": len(msgs),
                    "roles": roles,
                    "has_user": any(r == "user" for r in roles),
                    "stubbed_tools": sum(
                        1
                        for m in msgs
                        if isinstance(m, dict)
                        and m.get("role") == "tool"
                        and str(m.get("content") or "").startswith("[Earlier knowledge-base")
                    ),
                    "runId": "post-fix",
                },
            )
        elif isinstance(frame, FunctionCallResultFrame):
            result = getattr(frame, "result", None)
            dbg(
                "C",
                f"main.py:{self._probe}",
                "function_call_result",
                {
                    "direction": str(direction),
                    "name": getattr(frame, "function_name", None),
                    "result_type": type(result).__name__,
                    "result_chars": len(str(result)) if result is not None else 0,
                    "runId": "post-fix",
                },
            )
        elif isinstance(frame, LLMFullResponseStartFrame):
            dbg(
                "E",
                f"main.py:{self._probe}",
                "llm_response_start",
                {"direction": str(direction), "runId": "post-fix"},
            )
        elif isinstance(frame, LLMFullResponseEndFrame):
            dbg(
                "E",
                f"main.py:{self._probe}",
                "llm_response_end",
                {"direction": str(direction), "runId": "post-fix"},
            )
        elif isinstance(frame, TextFrame):
            # Skip transcription subclasses already logged above.
            if not isinstance(frame, TranscriptionFrame):
                text = getattr(frame, "text", "") or ""
                if text.strip():
                    dbg(
                        "E",
                        f"main.py:{self._probe}",
                        "text_frame",
                        {
                            "direction": str(direction),
                            "chars": len(text),
                            "preview": text[:80],
                            "runId": "post-fix",
                        },
                    )
        await self.push_frame(frame, direction)


# #endregion

transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


def _require_keys() -> None:
    settings = get_settings()
    missing = []
    if not settings.groq_api_key.strip():
        missing.append("GROQ_API_KEY")
    if not settings.deepgram_api_key.strip():
        missing.append("DEEPGRAM_API_KEY")
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Build and run the Glancy Fawcett voice pipeline."""
    _require_keys()
    settings = get_settings()
    logger.info("Starting Glancy voice bot")

    stt = DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        settings=DeepgramSTTService.Settings(
            model="nova-3-general",
            language="en",
            punctuate=True,
            smart_format=True,
        ),
    )

    llm = GroqLLMService(
        api_key=settings.groq_api_key,
        settings=GroqLLMService.Settings(
            model=settings.groq_model,
            system_instruction=VOICE_SYSTEM_PROMPT,
            max_tokens=512,
        ),
    )

    tts = DeepgramTTSService(
        api_key=settings.deepgram_api_key,
        settings=DeepgramTTSService.Settings(
            voice=settings.deepgram_tts_voice,
        ),
    )

    context = LLMContext(tools=[search_site_kb])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    # #region agent log
    @user_aggregator.event_handler("on_user_turn_stopped")
    async def _dbg_user_turn_stopped(aggregator, strategy, message):
        content = getattr(message, "content", None)
        dbg(
            "F",
            "main.py:user_turn_stopped",
            "user_turn_stopped",
            {
                "strategy": str(strategy),
                "content_chars": len(content or ""),
                "content_preview": (content or "")[:120],
                "runId": "post-fix",
            },
        )

    @user_aggregator.event_handler("on_user_turn_inference_triggered")
    async def _dbg_user_inference(aggregator, strategy):
        dbg(
            "F",
            "main.py:user_inference",
            "user_inference_triggered",
            {"strategy": str(strategy), "runId": "post-fix"},
        )

    # #endregion

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            DebugProbeProcessor("post_stt"),
            user_aggregator,
            ContextTrimProcessor(context),  # user -> LLM
            DebugProbeProcessor("pre_llm"),
            llm,
            DebugProbeProcessor("post_llm"),
            ContextTrimProcessor(context),  # tool-result -> LLM (upstream)
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        context.add_message(
            {
                "role": "developer",
                "content": (
                    "Greet the user briefly as the Glancy Fawcett voice assistant "
                    "and offer to help with showrooms, products, or services."
                ),
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments) -> None:
    """Entry point used by the Pipecat development runner."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
