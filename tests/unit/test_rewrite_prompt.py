"""
Unit tests for rewrite mode prompt generation.
"""
import pytest
from leviathan.rewrite_mode import create_rewrite_prompt


class MockTask:
    """Mock task object for testing."""
    def __init__(self, allowed_paths):
        self.id = "test-task"
        self.title = "Test Task"
        self.scope = "test"
        self.priority = "high"
        self.estimated_size = "small"
        self.allowed_paths = allowed_paths
        self.acceptance_criteria = ["Criterion 1", "Criterion 2"]


class TestRewritePrompt:
    """Test prompt generation with filetype awareness."""
    
    def test_prompt_includes_python_instructions(self):
        """Prompt should include Python-specific instructions when .py files present."""
        task = MockTask(["tests/unit/test_example.py", "config.json"])
        existing_files = {
            "tests/unit/test_example.py": None,
            "config.json": None
        }
        
        prompt = create_rewrite_prompt(task, existing_files)
        
        # Should include Python-specific instructions
        assert "PYTHON FILES (.py)" in prompt
        assert "valid Python 3.10+ source code" in prompt
        assert "NO JSON-like escaped fragments" in prompt
        assert "Use Python dict/list literals directly" in prompt
        assert 'not {{\\"key\\": \\"value\\"}}' in prompt
    
    def test_prompt_includes_json_instructions(self):
        """Prompt should include JSON-specific instructions when .json files present."""
        task = MockTask(["config.json", "data.json"])
        existing_files = {
            "config.json": None,
            "data.json": None
        }
        
        prompt = create_rewrite_prompt(task, existing_files)
        
        # Should include JSON-specific instructions
        assert "JSON FILES (.json)" in prompt
        assert "valid JSON" in prompt
    
    def test_prompt_includes_yaml_instructions(self):
        """Prompt should include YAML-specific instructions when .yaml files present."""
        task = MockTask(["config.yaml", "settings.yml"])
        existing_files = {
            "config.yaml": None,
            "settings.yml": None
        }
        
        prompt = create_rewrite_prompt(task, existing_files)
        
        # Should include YAML-specific instructions
        assert "YAML FILES" in prompt
        assert "valid YAML" in prompt
    
    def test_prompt_with_mixed_filetypes(self):
        """Prompt should include all relevant instructions for mixed file types."""
        task = MockTask([
            "tests/unit/test_schema.py",
            "schemas/dataset.json",
            "config.yaml"
        ])
        existing_files = {
            "tests/unit/test_schema.py": None,
            "schemas/dataset.json": None,
            "config.yaml": None
        }
        
        prompt = create_rewrite_prompt(task, existing_files)
        
        # Should include all three filetype sections
        assert "PYTHON FILES (.py)" in prompt
        assert "JSON FILES (.json)" in prompt
        assert "YAML FILES" in prompt
    
    def test_prompt_includes_python_example(self):
        """Prompt should include example showing Python dict literal."""
        task = MockTask(["test.py"])
        existing_files = {"test.py": None}
        
        prompt = create_rewrite_prompt(task, existing_files)
        
        # Should include example with Python test file
        assert "test_example.py" in prompt
        assert "Example showing Python test file with dict literal" in prompt
    
    def test_prompt_without_special_filetypes(self):
        """Prompt should work without filetype-specific instructions for unknown types."""
        task = MockTask(["README.md", "data.txt"])
        existing_files = {
            "README.md": None,
            "data.txt": None
        }
        
        prompt = create_rewrite_prompt(task, existing_files)
        
        # Should not include filetype-specific sections
        assert "PYTHON FILES" not in prompt
        assert "JSON FILES" not in prompt
        assert "YAML FILES" not in prompt
        
        # But should still have basic structure
        assert "TASK DETAILS" in prompt
        assert "OUTPUT FORMAT" in prompt
