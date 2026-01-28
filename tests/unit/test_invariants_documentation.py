"""
Unit tests for documentation invariants.

Tests that canonical documentation structure is enforced.
"""
import pytest
import tempfile
from pathlib import Path

from tools.invariants_check import InvariantsChecker


class TestDocumentationInvariants:
    """Test documentation invariants enforcement."""
    
    def test_required_canonical_docs_exist(self):
        """Required canonical docs must exist."""
        repo_root = Path(__file__).parent.parent.parent
        
        checker = InvariantsChecker(repo_root)
        checker.check_documentation_invariants()
        
        # Should have no failures
        assert len(checker.failures) == 0
    
    def test_canonical_overview_references_key_docs(self):
        """Canonical overview must reference key docs."""
        repo_root = Path(__file__).parent.parent.parent
        
        overview_file = repo_root / 'docs' / '00_CANONICAL_OVERVIEW.md'
        assert overview_file.exists()
        
        with open(overview_file, 'r') as f:
            content = f.read()
        
        # Must reference invariants doc
        assert '07_INVARIANTS_AND_GUARDRAILS.md' in content
        
        # Must reference handover doc
        assert '13_HANDOVER_START_HERE.md' in content
    
    def test_missing_required_doc_fails(self):
        """Missing required canonical doc should fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            
            # Create minimal structure
            docs_dir = repo_root / "docs"
            docs_dir.mkdir()
            ops_dir = repo_root / "ops"
            ops_dir.mkdir()
            
            # Create invariants.yaml (minimal)
            (ops_dir / "invariants.yaml").write_text("kubernetes: {}\n")
            
            # Create only one of the required docs
            (docs_dir / "00_CANONICAL_OVERVIEW.md").write_text("# Overview\n")
            
            # Missing: 07_INVARIANTS_AND_GUARDRAILS.md and 13_HANDOVER_START_HERE.md
            
            checker = InvariantsChecker(repo_root)
            checker.check_documentation_invariants()
            
            # Should have failures for missing docs
            assert len(checker.failures) >= 2
            assert any('07_INVARIANTS_AND_GUARDRAILS.md' in failure for failure in checker.failures)
            assert any('13_HANDOVER_START_HERE.md' in failure for failure in checker.failures)
    
    def test_overview_missing_references_fails(self):
        """Canonical overview missing key references should fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            
            # Create minimal structure
            docs_dir = repo_root / "docs"
            docs_dir.mkdir()
            ops_dir = repo_root / "ops"
            ops_dir.mkdir()
            
            # Create invariants.yaml (minimal)
            (ops_dir / "invariants.yaml").write_text("kubernetes: {}\n")
            
            # Create all required docs
            (docs_dir / "00_CANONICAL_OVERVIEW.md").write_text("# Overview\nNo references here\n")
            (docs_dir / "07_INVARIANTS_AND_GUARDRAILS.md").write_text("# Invariants\n")
            (docs_dir / "13_HANDOVER_START_HERE.md").write_text("# Handover\n")
            
            checker = InvariantsChecker(repo_root)
            checker.check_documentation_invariants()
            
            # Should have failures for missing references
            assert len(checker.failures) >= 2
            assert any('must reference 07_INVARIANTS_AND_GUARDRAILS.md' in failure for failure in checker.failures)
            assert any('must reference 13_HANDOVER_START_HERE.md' in failure for failure in checker.failures)
    
    def test_all_required_docs_with_references_passes(self):
        """All required docs with proper references should pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            
            # Create minimal structure
            docs_dir = repo_root / "docs"
            docs_dir.mkdir()
            ops_dir = repo_root / "ops"
            ops_dir.mkdir()
            
            # Create invariants.yaml (minimal)
            (ops_dir / "invariants.yaml").write_text("kubernetes: {}\n")
            
            # Create all required docs with proper references
            overview_content = """# Overview
            
See [07_INVARIANTS_AND_GUARDRAILS.md](07_INVARIANTS_AND_GUARDRAILS.md)
See [13_HANDOVER_START_HERE.md](13_HANDOVER_START_HERE.md)
"""
            (docs_dir / "00_CANONICAL_OVERVIEW.md").write_text(overview_content)
            (docs_dir / "07_INVARIANTS_AND_GUARDRAILS.md").write_text("# Invariants\n")
            (docs_dir / "13_HANDOVER_START_HERE.md").write_text("# Handover\n")
            
            checker = InvariantsChecker(repo_root)
            checker.check_documentation_invariants()
            
            # Should have no failures
            assert len(checker.failures) == 0
