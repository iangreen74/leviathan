"""
Unit tests for atomic file writes in rewrite mode.
"""
import pytest
import tempfile
from pathlib import Path
from leviathan.rewrite_mode import write_files


class TestAtomicWrites:
    """Test atomic file writing behavior."""
    
    def test_write_single_file(self, tmp_path):
        """Test writing a single file."""
        files = {"test.txt": "Hello, world!"}
        written = write_files(files, tmp_path)
        
        assert len(written) == 1
        assert "test.txt" in written
        
        content = (tmp_path / "test.txt").read_text()
        assert content == "Hello, world!\n"
    
    def test_write_multiple_files(self, tmp_path):
        """Test writing multiple files."""
        files = {
            "file1.txt": "Content 1",
            "file2.txt": "Content 2",
            "subdir/file3.txt": "Content 3"
        }
        written = write_files(files, tmp_path)
        
        assert len(written) == 3
        assert (tmp_path / "file1.txt").read_text() == "Content 1\n"
        assert (tmp_path / "file2.txt").read_text() == "Content 2\n"
        assert (tmp_path / "subdir/file3.txt").read_text() == "Content 3\n"
    
    def test_trailing_newline_added(self, tmp_path):
        """Test that trailing newline is added if missing."""
        files = {"test.txt": "No newline"}
        write_files(files, tmp_path)
        
        content = (tmp_path / "test.txt").read_text()
        assert content == "No newline\n"
    
    def test_trailing_newline_preserved(self, tmp_path):
        """Test that existing trailing newline is preserved."""
        files = {"test.txt": "Has newline\n"}
        write_files(files, tmp_path)
        
        content = (tmp_path / "test.txt").read_text()
        assert content == "Has newline\n"
    
    def test_empty_file(self, tmp_path):
        """Test writing empty file."""
        files = {"empty.txt": ""}
        write_files(files, tmp_path)
        
        content = (tmp_path / "empty.txt").read_text()
        assert content == ""
    
    def test_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created."""
        files = {"deep/nested/path/file.txt": "content"}
        write_files(files, tmp_path)
        
        assert (tmp_path / "deep/nested/path/file.txt").exists()
        content = (tmp_path / "deep/nested/path/file.txt").read_text()
        assert content == "content\n"
    
    def test_overwrites_existing_file(self, tmp_path):
        """Test that existing files are overwritten."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Old content")
        
        files = {"test.txt": "New content"}
        write_files(files, tmp_path)
        
        content = test_file.read_text()
        assert content == "New content\n"
    
    def test_exact_content_preserved(self, tmp_path):
        """Test that exact content is preserved (except trailing newline)."""
        content_with_special_chars = "Line 1\nLine 2\n\tTabbed\n  Spaced"
        files = {"test.txt": content_with_special_chars}
        write_files(files, tmp_path)
        
        written_content = (tmp_path / "test.txt").read_text()
        assert written_content == content_with_special_chars + "\n"
    
    def test_no_trailing_newline_option(self, tmp_path):
        """Test disabling trailing newline addition."""
        files = {"test.txt": "No newline"}
        write_files(files, tmp_path, ensure_trailing_newline=False)
        
        content = (tmp_path / "test.txt").read_text()
        assert content == "No newline"
