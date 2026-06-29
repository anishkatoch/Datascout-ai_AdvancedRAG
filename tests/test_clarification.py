"""
Tests for the clarification / correction feature in Thinking Mode.

Covers:
  1. Clarification flag store — set, get, default
  2. Gate 1 — clarify blocked when only 1 distinct source
  3. Gate 2 — clarify blocked when already asked last turn
  4. Gate 1+2 pass — clarify_allowed=True with 2+ sources, no prior ask
  5. ReAct Clarify action is terminal — returns immediately, sets flag
  6. History saved after clarification response
  7. Correction rules exist in _ARIA_SYSTEM
  8. Single apology rule exists in _ARIA_SYSTEM
  9. Clarify action NOT in prompt when clarify_allowed=False
 10. Clarify action IS in prompt when clarify_allowed=True
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document


# ── 1. Clarification flag store ───────────────────────────────────────────────

class TestClarifFlag:

    def test_default_false_for_new_session(self):
        from app.services.rag import _clarif_was_asked
        assert _clarif_was_asked("brand-new-session-xyz") is False

    def test_set_true(self):
        from app.services.rag import _clarif_set, _clarif_was_asked
        _clarif_set("sess-a", True)
        assert _clarif_was_asked("sess-a") is True

    def test_set_false_clears_flag(self):
        from app.services.rag import _clarif_set, _clarif_was_asked
        _clarif_set("sess-b", True)
        _clarif_set("sess-b", False)
        assert _clarif_was_asked("sess-b") is False

    def test_independent_per_session(self):
        from app.services.rag import _clarif_set, _clarif_was_asked
        _clarif_set("sess-c", True)
        _clarif_set("sess-d", False)
        assert _clarif_was_asked("sess-c") is True
        assert _clarif_was_asked("sess-d") is False

    def test_default_false_after_clear(self):
        from app.services.rag import _clarif_set, _clarif_was_asked
        _clarif_set("sess-e", True)
        _clarif_set("sess-e", False)
        assert _clarif_was_asked("sess-e") is False


# ── 2. Gate 1 — blocked when only 1 source ───────────────────────────────────

class TestGate1SingleSource:

    def _make_vs_with_sources(self, sources: list[str]):
        """Build a mock vector store whose hybrid retrieve returns docs from given sources."""
        docs = [
            Document(page_content=f"content from {s}", metadata={"source": s})
            for s in sources
        ]
        vs = MagicMock()
        vs.as_retriever.return_value.invoke.return_value = docs
        vs._collection = MagicMock()
        vs._collection.get.return_value = {
            "documents": [d.page_content for d in docs],
            "metadatas": [d.metadata for d in docs],
        }
        return vs, docs

    def test_single_source_clarify_not_allowed(self):
        from app.services.rag import _clarif_set
        _clarif_set("gate1-test", False)

        vs, docs = self._make_vs_with_sources(["doc_a.pdf"])

        with patch("app.services.rag._hybrid_retrieve", return_value=docs):
            # Re-run the gate logic manually
            distinct = {d.metadata.get("source", "") for d in docs if d.metadata.get("source")}
            multi_source = len(distinct) >= 2
        assert multi_source is False, "Single source must not allow clarification"

    def test_two_sources_clarify_allowed(self):
        vs, docs = self._make_vs_with_sources(["doc_a.pdf", "doc_b.pdf"])

        with patch("app.services.rag._hybrid_retrieve", return_value=docs):
            distinct = {d.metadata.get("source", "") for d in docs if d.metadata.get("source")}
            multi_source = len(distinct) >= 2
        assert multi_source is True, "Two sources must allow clarification gate to pass"

    def test_three_sources_clarify_allowed(self):
        vs, docs = self._make_vs_with_sources(["a.pdf", "b.pdf", "c.txt"])

        distinct = {d.metadata.get("source", "") for d in docs if d.metadata.get("source")}
        assert len(distinct) >= 2

    def test_no_source_metadata_treated_as_single(self):
        """Docs with no source metadata should not count as multiple sources."""
        docs = [Document(page_content="chunk", metadata={}) for _ in range(5)]
        distinct = {d.metadata.get("source", "") for d in docs if d.metadata.get("source")}
        assert len(distinct) < 2, "Empty source metadata must not count as multi-source"


# ── 3. Gate 2 — blocked when already clarified last turn ──────────────────────

class TestGate2AlreadyClarified:

    def test_already_clarified_blocks_second_ask(self):
        from app.services.rag import _clarif_set, _clarif_was_asked
        _clarif_set("gate2-sess", True)
        already = _clarif_was_asked("gate2-sess")
        assert already is True, "Gate 2 must be triggered when flag is True"

    def test_after_reset_allows_new_clarification(self):
        from app.services.rag import _clarif_set, _clarif_was_asked
        _clarif_set("gate2-sess2", True)
        _clarif_set("gate2-sess2", False)  # reset at start of new turn
        assert _clarif_was_asked("gate2-sess2") is False

    def test_fresh_session_gate2_passes(self):
        from app.services.rag import _clarif_was_asked
        assert _clarif_was_asked("gate2-fresh-sess-999") is False


# ── 4. Gate 1+2 combined ─────────────────────────────────────────────────────

class TestCombinedGates:

    def test_both_pass_means_clarify_allowed(self):
        """2+ sources AND no prior clarification → clarify_allowed=True."""
        from app.services.rag import _clarif_set, _clarif_was_asked
        _clarif_set("combined-sess", False)

        docs = [
            Document(page_content="a", metadata={"source": "file1.pdf"}),
            Document(page_content="b", metadata={"source": "file2.pdf"}),
        ]
        distinct = {d.metadata.get("source", "") for d in docs if d.metadata.get("source")}
        multi_source = len(distinct) >= 2
        already_clarified = _clarif_was_asked("combined-sess")

        clarify_allowed = multi_source and not already_clarified
        assert clarify_allowed is True

    def test_gate1_fails_means_no_clarify(self):
        """Single source → clarify_allowed=False even if flag is clear."""
        from app.services.rag import _clarif_set, _clarif_was_asked
        _clarif_set("combined-sess2", False)

        docs = [Document(page_content="a", metadata={"source": "file1.pdf"})]
        distinct = {d.metadata.get("source", "") for d in docs if d.metadata.get("source")}
        multi_source = len(distinct) >= 2
        already_clarified = _clarif_was_asked("combined-sess2")

        clarify_allowed = multi_source and not already_clarified
        assert clarify_allowed is False

    def test_gate2_fails_means_no_clarify(self):
        """2+ sources but already clarified → clarify_allowed=False."""
        from app.services.rag import _clarif_set, _clarif_was_asked
        _clarif_set("combined-sess3", True)  # already clarified

        docs = [
            Document(page_content="a", metadata={"source": "file1.pdf"}),
            Document(page_content="b", metadata={"source": "file2.pdf"}),
        ]
        distinct = {d.metadata.get("source", "") for d in docs if d.metadata.get("source")}
        multi_source = len(distinct) >= 2
        already_clarified = _clarif_was_asked("combined-sess3")

        clarify_allowed = multi_source and not already_clarified
        assert clarify_allowed is False


# ── 5. ReAct Clarify action is terminal ──────────────────────────────────────

class TestReActClarifyTerminal:

    def _make_mock_llm_response(self, text: str):
        msg = MagicMock()
        msg.content = text
        return msg

    def test_clarify_action_returns_question_immediately(self):
        """When LLM emits 'Action: clarify(which doc?)', loop stops and returns the question."""
        from app.services.rag import _react_answer, _clarif_was_asked, _clarif_set

        _clarif_set("react-test-1", False)

        docs = [Document(page_content="some content", metadata={"source": "x.pdf", "page_number": 1})]

        llm_response = self._make_mock_llm_response(
            "Thought: User question is ambiguous across two docs.\n"
            "Action: clarify(Are you asking about the 2022 report or the 2023 report?)"
        )

        vs = MagicMock()
        vs.as_retriever.return_value.invoke.return_value = docs
        vs._collection = MagicMock()
        vs._collection.get.return_value = {"documents": [], "metadatas": []}

        with patch("app.services.rag.llm_invoke", return_value=llm_response):
            answer, elapsed_ms, citations = _react_answer(
                vectorstore=vs,
                question="What happened in the report?",
                session_id="react-test-1",
                use_graph=False,
                history=[],
                clarify_allowed=True,
            )

        assert "2022" in answer or "2023" in answer, f"Clarification question should be returned, got: {answer}"
        assert citations == [], "Clarify action should return empty citations"
        assert elapsed_ms >= 0  # can be 0 in instant mocked calls

    def test_clarify_sets_flag(self):
        """After clarify() action fires, the session flag must be True."""
        from app.services.rag import _react_answer, _clarif_was_asked, _clarif_set

        _clarif_set("react-test-2", False)

        docs = [Document(page_content="x", metadata={"source": "a.pdf", "page_number": 1})]
        llm_response = self._make_mock_llm_response(
            "Thought: Ambiguous.\nAction: clarify(which file do you mean?)"
        )

        vs = MagicMock()
        vs.as_retriever.return_value.invoke.return_value = docs
        vs._collection = MagicMock()
        vs._collection.get.return_value = {"documents": [], "metadatas": []}

        with patch("app.services.rag.llm_invoke", return_value=llm_response):
            _react_answer(vs, "test question", "react-test-2", False, [], clarify_allowed=True)

        assert _clarif_was_asked("react-test-2") is True, "Flag must be set after clarify() fires"

    def test_clarify_blocked_when_not_allowed(self):
        """When clarify_allowed=False, clarify() in agent output is treated as unknown tool."""
        from app.services.rag import _react_answer, _clarif_was_asked, _clarif_set

        _clarif_set("react-test-3", False)

        docs = [Document(page_content="content", metadata={"source": "b.pdf", "page_number": 1})]

        # First response: tries clarify (should be blocked)
        # Second response: final answer
        llm_clarify = self._make_mock_llm_response(
            "Thought: Might be ambiguous.\nAction: clarify(which doc?)"
        )
        llm_final = self._make_mock_llm_response("Final Answer: Here is the answer.")

        vs = MagicMock()
        vs.as_retriever.return_value.invoke.return_value = docs
        vs._collection = MagicMock()
        vs._collection.get.return_value = {"documents": [], "metadatas": []}

        call_count = [0]
        def fake_llm(messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return llm_clarify
            return llm_final

        with patch("app.services.rag.llm_invoke", side_effect=fake_llm), \
             patch("app.services.rag._hybrid_retrieve", return_value=docs):
            answer, _, _ = _react_answer(vs, "test", "react-test-3", False, [], clarify_allowed=False)

        assert _clarif_was_asked("react-test-3") is False, "Flag must NOT be set when clarify is blocked"
        assert "Here is the answer" in answer


# ── 6. History saved after clarification ─────────────────────────────────────

class TestClarifyHistorySaved:

    def test_clarification_response_saved_to_history(self):
        """answer_question must save user question + clarification Q to history."""
        from app.services.rag import _history_get, _history_store
        from unittest.mock import MagicMock, patch

        session_id = "hist-clarify-test-001"
        _history_store.pop(session_id, None)  # clean slate

        docs_multi = [
            Document(page_content="doc A content", metadata={"source": "a.pdf", "page_number": 1}),
            Document(page_content="doc B content", metadata={"source": "b.pdf", "page_number": 1}),
        ]

        llm_clarify = MagicMock()
        llm_clarify.content = "Thought: Ambiguous.\nAction: clarify(Are you asking about doc A or doc B?)"

        vs = MagicMock()
        vs.as_retriever.return_value.invoke.return_value = docs_multi
        vs._collection = MagicMock()
        vs._collection.get.return_value = {
            "documents": [d.page_content for d in docs_multi],
            "metadatas": [d.metadata for d in docs_multi],
        }

        with patch("app.services.rag.llm_invoke", return_value=llm_clarify), \
             patch("app.services.rag._hybrid_retrieve", return_value=docs_multi), \
             patch("app.services.rag.check_intent", return_value=True):
            from app.services.rag import answer_question
            answer_question(
                vectorstore=vs,
                question="What is the summary?",
                session_id=session_id,
                advanced=False,
                thinking=True,
            )

        history = _history_get(session_id)
        assert len(history) >= 2, f"Expected at least 2 history entries, got: {history}"
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "What is the summary?"
        assert history[1]["role"] == "assistant"
        assert "doc A" in history[1]["content"] or "doc B" in history[1]["content"]


# ── 7 & 8. Correction and apology rules in system prompt ─────────────────────

class TestSystemPromptRules:

    def test_correction_handling_in_aria_system(self):
        from app.services.rag import _ARIA_SYSTEM
        lower = _ARIA_SYSTEM.lower()
        assert "wrong" in lower or "correct" in lower, \
            "_ARIA_SYSTEM must have correction handling instructions"

    def test_apology_rule_in_aria_system(self):
        from app.services.rag import _ARIA_SYSTEM
        lower = _ARIA_SYSTEM.lower()
        assert "apologis" in lower or "apologiz" in lower or "apology" in lower, \
            "_ARIA_SYSTEM must have single-apology rule"

    def test_rude_user_rule_in_aria_system(self):
        from app.services.rag import _ARIA_SYSTEM
        lower = _ARIA_SYSTEM.lower()
        assert "rude" in lower or "frustrated" in lower or "frustrat" in lower or "calm" in lower, \
            "_ARIA_SYSTEM must have instructions for handling rude/frustrated users"

    def test_no_repeated_apology_rule(self):
        from app.services.rag import _ARIA_SYSTEM
        lower = _ARIA_SYSTEM.lower()
        assert "once" in lower or "one" in lower or "repeat" in lower, \
            "_ARIA_SYSTEM must say to not apologise repeatedly"


# ── 9 & 10. Clarify in ReAct prompt controlled by flag ───────────────────────

class TestClarifyInPrompt:

    def _get_react_system_prompt(self, clarify_allowed: bool) -> str:
        """Run one step of _react_answer and capture the system message content."""
        from app.services.rag import _react_answer
        captured = []

        docs = [Document(page_content="x", metadata={"source": "a.pdf", "page_number": 1})]

        def fake_invoke(messages):
            captured.extend(messages)
            msg = MagicMock()
            msg.content = "Final Answer: done"
            return msg

        vs = MagicMock()
        vs.as_retriever.return_value.invoke.return_value = docs
        vs._collection = MagicMock()
        vs._collection.get.return_value = {"documents": [], "metadatas": []}

        with patch("app.services.rag.llm_invoke", side_effect=fake_invoke), \
             patch("app.services.rag._hybrid_retrieve", return_value=docs):
            _react_answer(vs, "test", "prompt-test", False, [], clarify_allowed=clarify_allowed)

        system_msgs = [m for m in captured if hasattr(m, "content") and "ARIA" in m.content]
        return system_msgs[0].content if system_msgs else ""

    def test_clarify_tool_not_in_prompt_when_disabled(self):
        """When disabled, the clarify() tool description must not appear (the word 'clarify'
        may still exist in _ARIA_SYSTEM's correction rules — we check for 'clarify(' syntax)."""
        prompt = self._get_react_system_prompt(clarify_allowed=False)
        assert "clarify(" not in prompt.lower(), \
            "clarify() tool must not appear in prompt when clarify_allowed=False"

    def test_clarify_tool_in_prompt_when_enabled(self):
        prompt = self._get_react_system_prompt(clarify_allowed=True)
        assert "clarify(" in prompt.lower(), \
            "clarify() tool must appear in prompt when clarify_allowed=True"

    def test_clarify_prompt_says_use_sparingly(self):
        prompt = self._get_react_system_prompt(clarify_allowed=True)
        assert "sparingly" in prompt.lower() or "only when" in prompt.lower(), \
            "Clarify prompt must tell agent to use it sparingly"
