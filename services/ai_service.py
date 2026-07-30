import json
import re
from dataclasses import dataclass
from typing import Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AIServiceError(RuntimeError):
    """Raised when an AI request or scheduling command is invalid."""


@dataclass(frozen=True)
class KnowledgeDocument:
    key: str
    title: str
    content: str


DEFAULT_KNOWLEDGE = (
    KnowledgeDocument(
        key="booking-policy",
        title="Booking policy",
        content=(
            "Members need an active unexpired membership and at least one credit. "
            "A scheduled future class can be booked only while capacity remains."
        ),
    ),
    KnowledgeDocument(
        key="cancellation-policy",
        title="Cancellation policy",
        content=(
            "A member may cancel a booked class before it starts. An eligible "
            "cancellation restores one consumed credit exactly once."
        ),
    ),
    KnowledgeDocument(
        key="roles",
        title="Studio roles",
        content=(
            "Managers administer members, trainers, renewals, and schedules. "
            "Members view their own status and manage only their own bookings. "
            "Trainers log in to manage their own workout slots and participants."
        ),
    ),
    KnowledgeDocument(
        key="workout-advice",
        title="General workout advice",
        content=(
            "Start at an appropriate intensity, use correct technique, warm up, "
            "cool down, stay hydrated, and allow recovery time. Members with pain "
            "or medical concerns should consult a qualified health professional."
        ),
    ),
)


class LightweightRetriever:
    """Dependency-free lexical retrieval suitable for the initial RAG foundation."""

    def __init__(self, documents: Iterable[KnowledgeDocument] = DEFAULT_KNOWLEDGE):
        self._documents = tuple(documents)

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(re.findall(r"[a-zA-Z0-9_]+", value.lower()))

    def retrieve(self, query: str, limit: int = 3) -> list[KnowledgeDocument]:
        query_tokens = self._tokens(query)
        ranked = sorted(
            self._documents,
            key=lambda document: len(
                query_tokens & self._tokens(f"{document.title} {document.content}")
            ),
            reverse=True,
        )
        return [
            document
            for document in ranked
            if query_tokens
            & self._tokens(f"{document.title} {document.content}")
        ][:limit]


class GroqAIService:
    """Groq chat client with local RAG and deterministic demo fallbacks."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float = 30,
        retriever: LightweightRetriever | None = None,
    ):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.retriever = retriever or LightweightRetriever()

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> "GroqAIService":
        return cls(
            api_key=str(config.get("GROQ_API_KEY", "")),
            model=str(config["GROQ_MODEL"]),
            timeout_seconds=float(config["GROQ_TIMEOUT_SECONDS"]),
        )

    def ask(
        self,
        question: str,
        extra_documents: Iterable[KnowledgeDocument] = (),
    ) -> str:
        if not question.strip():
            raise ValueError("Question is required.")

        documents = self.retriever.retrieve(question)
        extra_results = LightweightRetriever(extra_documents).retrieve(question)
        known_keys = {document.key for document in documents}
        documents.extend(
            document for document in extra_results if document.key not in known_keys
        )
        context = "\n\n".join(
            f"[{document.title}]\n{document.content}" for document in documents
        )
        system_prompt = (
            "You are a fitness studio assistant. Answer only from supplied context. "
            "If the context is insufficient, say that a manager should verify the "
            "information. Never invent availability, balances, or personal data."
        )
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Context:\n{context or 'No matching context.'}\n\n"
                    f"Question: {question.strip()}",
                },
            ],
        }
        if not self.api_key:
            return self._fallback_answer(documents)
        try:
            response = self._request(payload)
        except AIServiceError:
            return self._fallback_answer(documents)
        try:
            return str(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            return self._fallback_answer(documents)

    def health_check(self) -> bool:
        return bool(self.api_key)

    def recommend_workout(
        self,
        goal: str,
        member_profile: Mapping[str, object],
        available_classes: Iterable[Mapping[str, object]],
    ) -> str:
        """Recommend one real class using the member profile and live schedule."""

        if not goal.strip():
            raise ValueError("Tell the agent your training goal.")
        classes = list(available_classes)
        profile_text = (
            f"Name: {member_profile['name']}; credits: {member_profile['credits']}; "
            f"active membership: {member_profile['membership_active']}; "
            f"recent workouts: {member_profile.get('recent_workouts') or 'none'}."
        )
        schedule_text = "\n".join(
            f"{item['title']} ({item['specialty']}) on {item['starts_at']} "
            f"with {item['remaining_capacity']} spaces"
            for item in classes
        )
        documents = (
            KnowledgeDocument("member-profile", "Member profile", profile_text),
            KnowledgeDocument(
                "recommendation-schedule",
                "Classes available for recommendation",
                schedule_text or "No classes currently have free spaces.",
            ),
        )
        question = (
            f"Recommend one suitable scheduled workout for this member's goal: "
            f"{goal.strip()}. Explain the match briefly and include a safety reminder."
        )
        answer = self.ask(question, documents)
        if not answer.startswith("Demo assistant response:"):
            return answer
        return self._fallback_recommendation(goal, member_profile, classes)

    def parse_schedule_command(
        self, prompt: str, trainer_names: Iterable[str]
    ) -> dict[str, object]:
        """Extract scheduling arguments with Groq or a local deterministic parser."""

        if not prompt.strip():
            raise ValueError("Scheduling instruction is required.")
        available_trainers = tuple(trainer_names)
        names = ", ".join(available_trainers)
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract a weekly fitness class schedule command as JSON. "
                        "Return exactly these keys: trainer_name, title, weekday, "
                        "start_time in HH:MM format, max_capacity, occurrences, "
                        "duration_minutes. Use occurrences=4 unless explicitly "
                        "stated. Use duration_minutes=60 unless explicitly stated. "
                        f"Available trainers: {names}."
                    ),
                },
                {"role": "user", "content": prompt.strip()},
            ],
        }
        if not self.api_key:
            return self._fallback_schedule(prompt, available_trainers)
        try:
            response = self._request(payload)
            content = str(response["choices"][0]["message"]["content"]).strip()
            content = content.removeprefix("```json").removesuffix("```").strip()
            arguments = json.loads(content)
        except (AIServiceError, KeyError, IndexError, TypeError, json.JSONDecodeError):
            return self._fallback_schedule(prompt, available_trainers)
        if not isinstance(arguments, dict):
            return self._fallback_schedule(prompt, available_trainers)
        return arguments

    def _fallback_answer(self, documents: list[KnowledgeDocument]) -> str:
        if documents:
            facts = " ".join(document.content for document in documents[:2])
            return f"Demo assistant response: {facts}"
        return (
            "Demo assistant response: I do not have enough studio information to "
            "answer that confidently. Please ask a manager."
        )

    @staticmethod
    def _fallback_recommendation(
        goal: str,
        member_profile: Mapping[str, object],
        classes: list[Mapping[str, object]],
    ) -> str:
        if not member_profile["membership_active"] or int(member_profile["credits"]) < 1:
            return (
                "Recommendation: renew your membership or add credits before booking. "
                "After renewal, start with a class that matches your current ability."
            )
        if not classes:
            return (
                "Recommendation: no bookable classes are currently available. "
                "Check the weekly calendar again or ask a manager."
            )

        goal_words = set(re.findall(r"[a-zA-Z0-9_]+", goal.lower()))
        recommended = max(
            classes,
            key=lambda item: len(
                goal_words
                & set(
                    re.findall(
                        r"[a-zA-Z0-9_]+",
                        f"{item['title']} {item['specialty']}".lower(),
                    )
                )
            ),
        )
        return (
            f"Recommendation: {recommended['title']} on {recommended['starts_at']} "
            f"matches your goal of {goal.strip()}. Begin at a comfortable intensity, "
            "use correct technique, and tell the trainer about any pain or limitations."
        )

    def _fallback_schedule(
        self, prompt: str, trainer_names: tuple[str, ...]
    ) -> dict[str, object]:
        if not trainer_names:
            raise AIServiceError("No active trainers are available.")

        lowered = prompt.lower()
        trainer_name = next(
            (
                name
                for name in trainer_names
                if name.lower() in lowered
                or any(part.lower() in lowered for part in name.split())
            ),
            trainer_names[0],
        )
        title_match = re.search(
            r"schedule\s+(.+?)(?:\s+with|\s+every|\s+on|\s+at)", prompt, re.I
        )
        weekday_match = re.search(
            r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            prompt,
            re.I,
        )
        time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", prompt)
        capacity_match = re.search(r"capacity\s+(?:of\s+)?(\d+)", prompt, re.I)
        duration_match = re.search(r"(\d+)\s*(?:minutes?|mins?)", prompt, re.I)
        return {
            "trainer_name": trainer_name,
            "title": title_match.group(1).strip() if title_match else "Studio Class",
            "weekday": weekday_match.group(1).title() if weekday_match else "Tuesday",
            "start_time": (
                f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
                if time_match
                else "18:00"
            ),
            "max_capacity": int(capacity_match.group(1)) if capacity_match else 15,
            "occurrences": 4,
            "duration_minutes": (
                int(duration_match.group(1)) if duration_match else 60
            ),
        }

    def _request(self, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AIServiceError("Groq API is unavailable.") from exc
