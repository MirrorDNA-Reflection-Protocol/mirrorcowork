"""Tests for ReflectionRouter"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from mirrorcowork.router.reflection import (
    ReflectionPolicy,
    ReflectionRouter,
)
from mirrorcowork.state.task import (
    AgentCapability,
    ReflectionOutcome,
    Task,
    TaskIntent,
)


@pytest.fixture
def temp_state_dir():
    """Create a temporary state directory for tests"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def router(temp_state_dir):
    """Create a router with temporary state"""
    return ReflectionRouter(state_dir=temp_state_dir)


class TestReflectionRouter:
    """Tests for the ReflectionRouter"""

    @pytest.mark.asyncio
    async def test_simple_task_proceeds(self, router):
        """Simple tasks should proceed through reflection"""
        task = Task(
            description="Read the README file",
            source_client="test",
        )

        result = await router.submit(task)

        assert result.outcome == ReflectionOutcome.PROCEED
        assert result.task_id == task.id

    @pytest.mark.asyncio
    async def test_dangerous_pattern_rejected(self, router):
        """Tasks matching rejection patterns should be rejected"""
        task = Task(
            description="Run sudo rm -rf / to clean up",
            source_client="test",
        )

        result = await router.submit(task)

        assert result.outcome == ReflectionOutcome.REJECT
        assert "safety pattern" in result.notes.lower()

    @pytest.mark.asyncio
    async def test_escalation_pattern_escalates(self, router):
        """Tasks matching escalation patterns need human approval"""
        task = Task(
            description="Force push to the main branch",
            source_client="test",
        )

        result = await router.submit(task)

        assert result.outcome == ReflectionOutcome.ESCALATE
        assert "force push" in result.notes.lower()

    @pytest.mark.asyncio
    async def test_production_task_escalates(self, router):
        """Production-related tasks should escalate"""
        task = Task(
            description="Deploy the latest changes to production",
            source_client="test",
        )

        result = await router.submit(task)

        assert result.outcome == ReflectionOutcome.ESCALATE

    @pytest.mark.asyncio
    async def test_delete_task_escalates(self, router):
        """Delete operations should escalate"""
        task = Task(
            description="Delete old log files",
            source_client="test",
        )

        result = await router.submit(task)

        assert result.outcome == ReflectionOutcome.ESCALATE

    @pytest.mark.asyncio
    async def test_sensitive_capability_escalates(self, router):
        """Tasks requiring sensitive capabilities should escalate"""
        task = Task(
            description="Update the repository",
            source_client="test",
            required_capabilities=[AgentCapability.GIT_PUSH],
        )

        result = await router.submit(task)

        assert result.outcome == ReflectionOutcome.ESCALATE
        assert "sensitive" in result.notes.lower()

    @pytest.mark.asyncio
    async def test_trusted_client_bypass(self, temp_state_dir):
        """Trusted clients can bypass reflection for certain intents"""
        policy = ReflectionPolicy(
            trusted_clients={"claude_code": [TaskIntent.EXECUTE]}
        )
        router = ReflectionRouter(state_dir=temp_state_dir, policy=policy)

        task = Task(
            description="Run tests",
            source_client="claude_code",
            intent=TaskIntent.EXECUTE,
        )

        result = await router.submit(task)

        assert result.outcome == ReflectionOutcome.PROCEED
        assert "trusted client" in result.notes.lower()

    @pytest.mark.asyncio
    async def test_complex_task_decomposes(self, temp_state_dir):
        """Complex tasks should trigger decomposition"""
        policy = ReflectionPolicy(max_complexity_score=3)
        router = ReflectionRouter(state_dir=temp_state_dir, policy=policy)

        task = Task(
            description="First refactor the auth module and then update the tests and after that fix the documentation and finally deploy to staging",
            source_client="test",
            required_capabilities=[
                AgentCapability.CODE_WRITE,
                AgentCapability.FILE_WRITE,
                AgentCapability.GIT_COMMIT,
            ],
        )

        result = await router.submit(task)

        assert result.outcome in (ReflectionOutcome.DECOMPOSE, ReflectionOutcome.ESCALATE)

    @pytest.mark.asyncio
    async def test_queue_persistence(self, temp_state_dir):
        """Queue should persist across router instances"""
        router1 = ReflectionRouter(state_dir=temp_state_dir)
        task = Task(description="Test task", source_client="test")
        await router1.submit(task)

        # Create new router instance
        router2 = ReflectionRouter(state_dir=temp_state_dir)
        status = router2.get_queue_status()

        # Task should be in ready queue
        assert status["ready"] >= 1 or status["completed"] >= 1

    @pytest.mark.asyncio
    async def test_context_provider_called(self, temp_state_dir):
        """Custom context providers should be called during reflection"""
        router = ReflectionRouter(state_dir=temp_state_dir)

        context_called = False

        def mock_provider():
            nonlocal context_called
            context_called = True
            return {"system_state": {"test": True}}

        router.add_context_provider(mock_provider)

        task = Task(description="Test task", source_client="test")
        await router.submit(task)

        assert context_called

    @pytest.mark.asyncio
    async def test_reflection_hook_called(self, temp_state_dir):
        """Reflection hooks should be called"""
        router = ReflectionRouter(state_dir=temp_state_dir)

        hook_called = False
        hook_task = None

        def mock_hook(task, context):
            nonlocal hook_called, hook_task
            hook_called = True
            hook_task = task

        router.add_reflection_hook(mock_hook)

        task = Task(description="Test task", source_client="test")
        await router.submit(task)

        assert hook_called
        assert hook_task.id == task.id

    @pytest.mark.asyncio
    async def test_task_completion(self, router):
        """Tasks can be completed with results"""
        task = Task(description="Test task", source_client="test")
        await router.submit(task)

        result = {"success": True}
        completed = router.complete_task(task.id, result=result)

        assert completed is not None
        assert completed.result == result

    @pytest.mark.asyncio
    async def test_export_state(self, router):
        """Router state can be exported"""
        task = Task(description="Test task", source_client="test")
        await router.submit(task)

        state = router.export_state()

        assert "queue" in state
        assert "agents" in state
        assert "policy" in state
        assert "queue_status" in state


class TestAgentRegistry:
    """Tests for agent registration and capability matching"""

    def test_register_agent(self, router):
        """Agents can be registered with capabilities"""
        router.register_agent("claude_code", [
            AgentCapability.CODE_WRITE,
            AgentCapability.CODE_READ,
        ])

        caps = router.agents.get_capabilities("claude_code")

        assert AgentCapability.CODE_WRITE in caps
        assert AgentCapability.CODE_READ in caps

    def test_find_capable_agent(self, router):
        """Can find agents capable of handling requirements"""
        router.register_agent("claude_code", [
            AgentCapability.CODE_WRITE,
            AgentCapability.CODE_READ,
            AgentCapability.GIT_COMMIT,
        ])
        router.register_agent("reader_only", [
            AgentCapability.CODE_READ,
            AgentCapability.FILE_READ,
        ])

        capable = router.agents.find_capable([
            AgentCapability.CODE_WRITE,
            AgentCapability.GIT_COMMIT,
        ])

        assert "claude_code" in capable
        assert "reader_only" not in capable


class TestTask:
    """Tests for Task model"""

    def test_task_creation(self):
        """Tasks should be created with defaults"""
        task = Task(description="Test task")

        assert task.id.startswith("task_")
        assert task.intent == TaskIntent.EXECUTE
        assert task.source_client == "unknown"

    def test_mark_reflected(self):
        """Tasks can be marked as reflected"""
        task = Task(description="Test task")
        task.mark_reflected(
            ReflectionOutcome.PROCEED,
            notes="All good",
        )

        assert task.reflection_outcome == ReflectionOutcome.PROCEED
        assert task.reflection_notes == "All good"
        assert task.reflection_timestamp is not None

    def test_modified_description(self):
        """Reflected tasks can have modified descriptions"""
        task = Task(description="Original description")
        task.mark_reflected(
            ReflectionOutcome.MODIFY,
            modifications={"description": "Modified description"},
        )

        assert task.get_effective_description() == "Modified description"

    def test_should_execute(self):
        """Only PROCEED and MODIFY outcomes allow execution"""
        proceed_task = Task(description="Test")
        proceed_task.mark_reflected(ReflectionOutcome.PROCEED)
        assert proceed_task.should_execute()

        modify_task = Task(description="Test")
        modify_task.mark_reflected(ReflectionOutcome.MODIFY)
        assert modify_task.should_execute()

        reject_task = Task(description="Test")
        reject_task.mark_reflected(ReflectionOutcome.REJECT)
        assert not reject_task.should_execute()

        escalate_task = Task(description="Test")
        escalate_task.mark_reflected(ReflectionOutcome.ESCALATE)
        assert not escalate_task.should_execute()

    def test_handoff_dict(self):
        """Tasks can be converted to handoff format"""
        task = Task(
            description="Test task",
            source_client="claude_code",
            intent=TaskIntent.EXECUTE,
        )
        task.mark_reflected(ReflectionOutcome.PROCEED, notes="OK")

        handoff = task.to_handoff_dict()

        assert handoff["task_id"] == task.id
        assert handoff["description"] == "Test task"
        assert handoff["source"] == "claude_code"
        assert handoff["reflection"]["outcome"] == "proceed"
