"""Standalone Streamlit app helpers for somni-graph-quiz."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from somni_graph_quiz.adapters.streamlit.controller import StreamlitQuizController
from somni_graph_quiz.app.env_config import write_runtime_settings_to_env
from somni_graph_quiz.app.settings import ENV_PATH, GraphQuizSettings, get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BUSINESS9_QUESTIONNAIRE_PATH = PROJECT_ROOT / "data" / "questionnaire_business9.json"


def build_default_questionnaire() -> list[dict]:
    """Load the bundled questionnaire used by the standalone Streamlit app."""
    payload = json.loads(BUSINESS9_QUESTIONNAIRE_PATH.read_text(encoding="utf-8"))
    source_path = payload.get("canonical_questionnaire_path")
    if isinstance(source_path, str) and source_path:
        payload = json.loads((PROJECT_ROOT / "data" / source_path).read_text(encoding="utf-8"))
    questionnaire = payload.get("questionnaire")
    if not isinstance(questionnaire, list):
        raise ValueError("Bundled Streamlit questionnaire must include a questionnaire list")
    if len(questionnaire) != 9:
        raise ValueError("Bundled questionnaire must contain 9 questions")
    return questionnaire


def initialize_default_view(
    controller: StreamlitQuizController,
    *,
    session_id: str,
    language_preference: str,
    quiz_mode: str,
) -> dict:
    """Initialize a Streamlit session with the bundled questionnaire."""
    return controller.initialize_session(
        session_id=session_id,
        questionnaire=build_default_questionnaire(),
        language_preference=language_preference,
        quiz_mode=quiz_mode,
    )


def build_runtime_settings(
    form_state: dict[str, object] | None,
    *,
    defaults: GraphQuizSettings | None = None,
) -> GraphQuizSettings:
    """Merge runtime form values onto the current defaults."""
    base = defaults or get_settings()
    state = form_state or {}
    return GraphQuizSettings.model_validate(
        {
            "llm_base_url": state.get("llm_base_url", base.llm_base_url),
            "llm_api_key": state.get("llm_api_key", base.llm_api_key),
            "llm_model": state.get("llm_model", base.llm_model),
            "llm_temperature": state.get("llm_temperature", base.llm_temperature),
            "llm_timeout": state.get("llm_timeout", base.llm_timeout),
            "llm_reasoning_effort": state.get("llm_reasoning_effort", base.llm_reasoning_effort),
            "grpc_host": state.get("grpc_host", base.grpc_host),
            "grpc_port": state.get("grpc_port", base.grpc_port),
        }
    )


def persist_runtime_settings(
    form_state: dict[str, object],
    *,
    env_path: Path = ENV_PATH,
) -> GraphQuizSettings:
    """Persist runtime settings and clear the cached settings object."""
    settings = build_runtime_settings(form_state, defaults=GraphQuizSettings())
    write_runtime_settings_to_env(settings, env_path)
    get_settings.cache_clear()
    return settings


def main() -> None:
    """Run the standalone Streamlit shell."""
    import streamlit as st

    st.set_page_config(page_title="Somni Graph Quiz", page_icon=":zzz:", layout="centered")
    st.title("Somni Graph Quiz")
    runtime_settings = build_runtime_settings(st.session_state.get("runtime_settings"))

    if "controller" not in st.session_state:
        st.session_state["controller"] = StreamlitQuizController()
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = f"streamlit-{uuid4().hex[:12]}"
    if "language_preference" not in st.session_state:
        st.session_state["language_preference"] = "zh-CN"
    if "quiz_mode" not in st.session_state:
        st.session_state["quiz_mode"] = "dynamic"
    if "view" not in st.session_state:
        st.session_state["view"] = initialize_default_view(
            st.session_state["controller"],
            session_id=st.session_state["session_id"],
            language_preference=st.session_state["language_preference"],
            quiz_mode=st.session_state["quiz_mode"],
        )

    config_notice = st.session_state.pop("config_notice", None)
    config_error = st.session_state.pop("config_error", None)
    if config_notice:
        st.sidebar.success(config_notice)
    if config_error:
        st.sidebar.error(config_error)
    st.sidebar.selectbox(
        "Language",
        options=["zh-CN", "en"],
        key="language_preference",
    )
    st.sidebar.selectbox(
        "Quiz Mode",
        options=["dynamic"],
        key="quiz_mode",
    )
    with st.sidebar.form("runtime_config"):
        llm_base_url = st.text_input("Base URL", value=runtime_settings.llm_base_url, placeholder="https://...")
        llm_api_key = st.text_input("API Key", value=runtime_settings.llm_api_key, type="password")
        llm_model = st.text_input("Model", value=runtime_settings.llm_model)
        llm_temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=float(runtime_settings.llm_temperature),
            step=0.05,
        )
        llm_timeout = st.number_input(
            "Timeout (s)",
            min_value=1,
            max_value=300,
            value=int(runtime_settings.llm_timeout),
            step=1,
        )
        llm_reasoning_effort = st.selectbox(
            "Reasoning Effort",
            options=["minimal", "low", "medium", "high"],
            index=["minimal", "low", "medium", "high"].index(runtime_settings.llm_reasoning_effort)
            if runtime_settings.llm_reasoning_effort in {"minimal", "low", "medium", "high"}
            else 0,
        )
        save_config = st.form_submit_button("Apply LLM Config")

    if save_config:
        st.session_state["runtime_settings"] = {
            "llm_base_url": llm_base_url,
            "llm_api_key": llm_api_key,
            "llm_model": llm_model,
            "llm_temperature": llm_temperature,
            "llm_timeout": llm_timeout,
            "llm_reasoning_effort": llm_reasoning_effort,
            "grpc_host": runtime_settings.grpc_host,
            "grpc_port": runtime_settings.grpc_port,
        }
        try:
            saved_settings = persist_runtime_settings(st.session_state["runtime_settings"])
            st.session_state["controller"].refresh_runtime(
                session_id=st.session_state["session_id"],
                settings=saved_settings,
            )
        except OSError as exc:
            st.session_state["config_error"] = f"Failed to write .env: {exc}"
        else:
            st.session_state["config_notice"] = "LLM config applied and written to .env."
        st.rerun()

    if st.sidebar.button("Reset Session"):
        st.session_state["session_id"] = f"streamlit-{uuid4().hex[:12]}"
        st.session_state["view"] = initialize_default_view(
            st.session_state["controller"],
            session_id=st.session_state["session_id"],
            language_preference=st.session_state["language_preference"],
            quiz_mode=st.session_state["quiz_mode"],
        )
        st.rerun()

    view = st.session_state["view"]
    for message in view["chat_history"]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    pending_question = view.get("pending_question") or {}
    options = pending_question.get("options") or []
    if options and not view.get("finalized", False):
        st.subheader(pending_question.get("title", "Current question"))
        for option in options:
            label = option.get("label") or option.get("option_text") or option.get("option_id", "")
            if st.button(label, key=f'option-{pending_question.get("question_id")}-{option.get("option_id")}'):
                st.session_state["view"] = st.session_state["controller"].submit_direct_answer(
                    session_id=st.session_state["session_id"],
                    answer={
                        "question_id": pending_question.get("question_id", ""),
                        "selected_options": [option.get("option_id", "")],
                        "input_value": label,
                    },
                )
                st.rerun()

    prompt = "Message" if st.session_state["language_preference"].startswith("en") else "输入你的回答"
    user_message = st.chat_input(prompt, disabled=view.get("finalized", False))
    if user_message:
        st.session_state["view"] = st.session_state["controller"].submit_message(
            session_id=st.session_state["session_id"],
            message=user_message,
        )
        st.rerun()

    with st.expander("Answer Record", expanded=False):
        st.json(view.get("answer_record", {}))

    if view.get("finalized", False):
        st.success(view.get("assistant_message", "Completed"))
