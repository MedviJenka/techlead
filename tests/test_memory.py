"""Per-agent memory: business-scoped keys, bucket round-trips of real LanceDB files, and crew wiring."""

import shutil
from pathlib import Path

import pytest
from crewai import Memory
from crewai.memory.storage.lancedb_storage import LanceDBStorage
from crewai.memory.types import MemoryRecord

from ai.crews import AIRuntime, LeadIntelligenceCrew
from ai.data.sample_store import InMemoryLeadStore
from ai.memory import AgentMemoryStore, MemoryKey
from ai.skill_library import SkillLibrary
from tests.conftest import BUSINESS_ID
from tests.fakes import ScriptedLLM

KEY = MemoryKey(BUSINESS_ID, "LeadIntelligenceCrew", "scoring_agent")


class DirObjectStore:
    """A bucket backed by a local directory."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.uploads: list[str] = []

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")
                      if p.is_file() and p.relative_to(self.root).as_posix().startswith(prefix))

    def download(self, key: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.root / key, path)

    def upload(self, path: Path, key: str) -> None:
        (self.root / key).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, self.root / key)
        self.uploads.append(key)

    def delete_prefix(self, prefix: str) -> None:
        for key in self.list_keys(prefix):
            (self.root / key).unlink()


@pytest.fixture
def bucket(tmp_path: Path) -> DirObjectStore:
    return DirObjectStore(tmp_path / "bucket")


def remember(path: Path, content: str) -> None:
    LanceDBStorage(path=path, compact_every=0).save([MemoryRecord(content=content, embedding=[0.1, 0.2, 0.3])])


def recalled(path: Path) -> list[str]:
    return sorted(record.content for record in LanceDBStorage(path=path, compact_every=0).list_records())


class TestMemoryKey:
    def test_prefix_is_business_crew_agent(self) -> None:
        assert KEY.prefix == f"business/{BUSINESS_ID}/LeadIntelligenceCrew/scoring_agent/"

    @pytest.mark.parametrize("business_id", ["../other", "a/b", "", "biz 1"])
    def test_rejects_segments_that_escape_the_prefix(self, business_id: str) -> None:
        with pytest.raises(ValueError):
            MemoryKey(business_id, "LeadIntelligenceCrew", "scoring_agent")


class TestAgentMemoryStore:
    def test_memory_survives_a_new_process(self, tmp_path: Path, bucket: DirObjectStore) -> None:
        first = AgentMemoryStore(bucket, tmp_path / "cache-a")
        remember(first.path(KEY), "Prefers WhatsApp over calls")
        assert first.sync(KEY) > 0

        second = AgentMemoryStore(bucket, tmp_path / "cache-b")  # another process: empty cache
        second.memory(KEY, ScriptedLLM({}))

        assert recalled(second.path(KEY)) == ["Prefers WhatsApp over calls"]

    def test_sync_uploads_only_new_files(self, tmp_path: Path, bucket: DirObjectStore) -> None:
        store = AgentMemoryStore(bucket, tmp_path / "cache")
        store.memory(KEY, ScriptedLLM({}))
        remember(store.path(KEY), "first")
        store.sync(KEY)
        first_uploads = set(bucket.uploads)

        remember(store.path(KEY), "second")
        store.sync(KEY)

        assert set(bucket.uploads[len(first_uploads):]).isdisjoint(first_uploads)
        assert store.sync(KEY) == 0

    def test_downloaded_files_are_not_uploaded_back(self, tmp_path: Path, bucket: DirObjectStore) -> None:
        writer = AgentMemoryStore(bucket, tmp_path / "cache-a")
        remember(writer.path(KEY), "fact")
        writer.sync(KEY)
        bucket.uploads.clear()

        reader = AgentMemoryStore(bucket, tmp_path / "cache-b")
        reader.memory(KEY, ScriptedLLM({}))

        assert reader.sync(KEY) == 0

    def test_businesses_do_not_share_memory(self, tmp_path: Path, bucket: DirObjectStore) -> None:
        store = AgentMemoryStore(bucket, tmp_path / "cache")
        remember(store.path(KEY), "secret of business one")
        store.sync(KEY)

        other = MemoryKey("other_business", KEY.crew, KEY.agent)
        fresh = AgentMemoryStore(bucket, tmp_path / "cache-b")
        fresh.memory(other, ScriptedLLM({}))

        assert recalled(fresh.path(other)) == []

    def test_reset_forgets_in_bucket_and_cache(self, tmp_path: Path, bucket: DirObjectStore) -> None:
        store = AgentMemoryStore(bucket, tmp_path / "cache")
        remember(store.path(KEY), "fact")
        store.sync(KEY)

        store.reset(KEY)

        assert bucket.list_keys(KEY.prefix) == []
        assert not store.path(KEY).exists()


class TestCrewWiring:
    def make(self, store: InMemoryLeadStore, skills: SkillLibrary, memory: AgentMemoryStore | None
             ) -> LeadIntelligenceCrew:
        llm = ScriptedLLM({})
        return LeadIntelligenceCrew.for_business(AIRuntime(store, lambda tier: llm, skills, memory=memory),
                                                 BUSINESS_ID)

    def test_each_agent_gets_its_own_business_scoped_memory(
        self, tmp_path: Path, bucket: DirObjectStore, store: InMemoryLeadStore, skill_library: SkillLibrary
    ) -> None:
        memory = AgentMemoryStore(bucket, tmp_path / "cache")
        crew = self.make(store, skill_library, memory)

        agents = [crew.qualification_agent(), crew.scoring_agent(), crew.next_action_agent()]

        assert all(isinstance(agent.memory, Memory) for agent in agents)
        assert sorted(key.agent for key in crew._memory_keys) == [
            "next_action_agent", "qualification_agent", "scoring_agent"]
        assert {key.business_id for key in crew._memory_keys} == {BUSINESS_ID}

    def test_no_memory_store_means_no_memory(self, store: InMemoryLeadStore, skill_library: SkillLibrary) -> None:
        crew = self.make(store, skill_library, None)

        assert crew.scoring_agent().memory is None

    def test_failed_sync_does_not_fail_the_run(
        self, tmp_path: Path, store: InMemoryLeadStore, skill_library: SkillLibrary
    ) -> None:
        class BrokenBucket(DirObjectStore):
            def upload(self, path: Path, key: str) -> None:
                raise ConnectionError("storage down")

        memory = AgentMemoryStore(BrokenBucket(tmp_path / "bucket"), tmp_path / "cache")
        crew = self.make(store, skill_library, memory)
        crew.scoring_agent()
        remember(memory.path(KEY), "fact")

        crew.sync_memory()  # logs, does not raise
