"""
Unit tests for bootstrap indexer.
"""
import pytest
from pathlib import Path
from leviathan.bootstrap.indexer import (
    RepositoryIndexer,
    BootstrapConfig,
    load_bootstrap_config,
    FILE_TYPE_MAP
)


class TestBootstrapConfig:
    """Test bootstrap configuration loading."""
    
    def test_default_config(self):
        """Should use defaults when no config provided."""
        config = BootstrapConfig()
        assert config.include == ['**/*']
        assert '.git' in config.exclude
        assert 'node_modules' in config.exclude
        assert config.api_routes_enabled is True
    
    def test_custom_config(self):
        """Should load custom configuration."""
        config_dict = {
            'bootstrap': {
                'include': ['src/**', 'docs/**'],
                'exclude': ['.git', 'build'],
                'api_routes': {'enabled': False}
            }
        }
        config = BootstrapConfig(config_dict)
        assert config.include == ['src/**', 'docs/**']
        assert config.exclude == ['.git', 'build']
        assert config.api_routes_enabled is False


class TestRepositoryIndexer:
    """Test repository indexer."""
    
    def test_should_exclude(self, tmp_path):
        """Should correctly identify excluded paths."""
        indexer = RepositoryIndexer(tmp_path)
        
        # Should exclude
        assert indexer.should_exclude(Path('.git/config'))
        assert indexer.should_exclude(Path('node_modules/package'))
        assert indexer.should_exclude(Path('src/__pycache__/module.pyc'))
        
        # Should not exclude
        assert not indexer.should_exclude(Path('src/main.py'))
        assert not indexer.should_exclude(Path('README.md'))
    
    def test_classify_file_type(self, tmp_path):
        """Should classify file types correctly."""
        indexer = RepositoryIndexer(tmp_path)
        
        assert indexer.classify_file_type(Path('main.py')) == 'python'
        assert indexer.classify_file_type(Path('app.js')) == 'javascript'
        assert indexer.classify_file_type(Path('README.md')) == 'markdown'
        assert indexer.classify_file_type(Path('config.yaml')) == 'yaml'
        assert indexer.classify_file_type(Path('Dockerfile')) == 'dockerfile'
        assert indexer.classify_file_type(Path('unknown.xyz')) == 'unknown'
    
    def test_extract_markdown_title(self, tmp_path):
        """Should extract first markdown heading."""
        indexer = RepositoryIndexer(tmp_path)
        
        # Create test markdown file
        md_file = tmp_path / 'test.md'
        md_file.write_text('# Test Title\n\nSome content\n\n## Subtitle\n')
        
        title = indexer.extract_markdown_title(md_file)
        assert title == 'Test Title'
    
    def test_extract_markdown_title_no_heading(self, tmp_path):
        """Should return None if no heading found."""
        indexer = RepositoryIndexer(tmp_path)
        
        md_file = tmp_path / 'test.md'
        md_file.write_text('Just some text without headings')
        
        title = indexer.extract_markdown_title(md_file)
        assert title is None
    
    def test_parse_workflow_file(self, tmp_path):
        """Should parse GitHub Actions workflow."""
        indexer = RepositoryIndexer(tmp_path)
        
        # Create test workflow
        workflow_dir = tmp_path / '.github' / 'workflows'
        workflow_dir.mkdir(parents=True)
        workflow_file = workflow_dir / 'ci.yml'
        workflow_file.write_text('''name: CI
"on":
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
''')
        
        result = indexer.parse_workflow_file(workflow_file)
        assert result is not None
        assert result['name'] == 'CI'
        assert 'push' in result['triggers']
        assert 'pull_request' in result['triggers']
    
    def test_extract_fastapi_routes(self, tmp_path):
        """Should extract FastAPI routes via AST."""
        indexer = RepositoryIndexer(tmp_path)
        
        # Create test Python file with FastAPI routes
        py_file = tmp_path / 'api.py'
        py_file.write_text('''
from fastapi import FastAPI

app = FastAPI()

@app.get("/users")
def list_users():
    return []

@app.post("/users")
def create_user():
    return {}

@app.get("/health")
def health_check():
    return {"status": "ok"}
''')
        
        routes = indexer.extract_fastapi_routes(py_file)
        assert len(routes) == 3
        
        # Check GET /users
        get_users = next(r for r in routes if r['method'] == 'GET' and r['path'] == '/users')
        assert get_users['function_name'] == 'list_users'
        
        # Check POST /users
        post_users = next(r for r in routes if r['method'] == 'POST' and r['path'] == '/users')
        assert post_users['function_name'] == 'create_user'
    
    def test_extract_fastapi_routes_disabled(self, tmp_path):
        """Should not extract routes when disabled."""
        config = BootstrapConfig({'bootstrap': {'api_routes': {'enabled': False}}})
        indexer = RepositoryIndexer(tmp_path, config)
        
        py_file = tmp_path / 'api.py'
        py_file.write_text('@app.get("/test")\ndef test(): pass')
        
        routes = indexer.extract_fastapi_routes(py_file)
        assert len(routes) == 0
    
    def test_index_repository(self, tmp_path):
        """Should index repository and produce events."""
        # Create test repository structure
        (tmp_path / 'README.md').write_text('# Test Repo\n\nDescription')
        (tmp_path / 'src').mkdir()
        (tmp_path / 'src' / 'main.py').write_text('print("hello")')
        (tmp_path / 'docs').mkdir()
        (tmp_path / 'docs' / 'guide.md').write_text('# Guide\n\nContent')
        
        # Create workflow
        workflow_dir = tmp_path / '.github' / 'workflows'
        workflow_dir.mkdir(parents=True)
        (workflow_dir / 'test.yml').write_text('name: Test\non: push')
        
        # Index
        indexer = RepositoryIndexer(tmp_path)
        result = indexer.index_repository(
            target_id='test-repo',
            repo_url='git@github.com:test/repo.git',
            commit_sha='abc123',
            default_branch='main'
        )
        
        # Check events
        assert len(result['events']) > 0
        
        # Check for bootstrap.started
        started = next(e for e in result['events'] if e['event_type'] == 'bootstrap.started')
        assert started['payload']['target_id'] == 'test-repo'
        
        # Check for file.discovered events
        file_events = [e for e in result['events'] if e['event_type'] == 'file.discovered']
        assert len(file_events) >= 4  # README, main.py, guide.md, test.yml
        
        # Check for doc.discovered events
        doc_events = [e for e in result['events'] if e['event_type'] == 'doc.discovered']
        assert len(doc_events) >= 2  # README.md, guide.md
        
        # Check for workflow.discovered events
        workflow_events = [e for e in result['events'] if e['event_type'] == 'workflow.discovered']
        assert len(workflow_events) >= 1
        
        # Check for repo.indexed
        indexed = next(e for e in result['events'] if e['event_type'] == 'repo.indexed')
        assert indexed['payload']['files_count'] >= 4
        
        # Check for bootstrap.completed
        completed = next(e for e in result['events'] if e['event_type'] == 'bootstrap.completed')
        assert completed['payload']['status'] == 'completed'
        
        # Check artifacts
        assert 'repo_tree.txt' in result['artifacts']
        assert 'repo_manifest.json' in result['artifacts']
        
        # Check manifest
        assert result['manifest']['target_id'] == 'test-repo'
        assert result['manifest']['counts']['total_files'] >= 4
        assert result['manifest']['counts']['docs'] >= 2
    
    def test_index_repository_excludes_git(self, tmp_path):
        """Should exclude .git directory."""
        # Create .git directory
        (tmp_path / '.git').mkdir()
        (tmp_path / '.git' / 'config').write_text('test')
        (tmp_path / 'src').mkdir()
        (tmp_path / 'src' / 'main.py').write_text('print("hello")')
        
        indexer = RepositoryIndexer(tmp_path)
        result = indexer.index_repository(
            target_id='test',
            repo_url='test',
            commit_sha='abc',
            default_branch='main'
        )
        
        # Check that .git files are not in events
        file_events = [e for e in result['events'] if e['event_type'] == 'file.discovered']
        git_files = [e for e in file_events if '.git' in e['payload']['file_path']]
        assert len(git_files) == 0


class TestLoadBootstrapConfig:
    """Test bootstrap config loading from file."""
    
    def test_load_config_file(self, tmp_path):
        """Should load config from .leviathan/bootstrap.yaml."""
        leviathan_dir = tmp_path / '.leviathan'
        leviathan_dir.mkdir()
        
        config_file = leviathan_dir / 'bootstrap.yaml'
        config_file.write_text('''
bootstrap:
  include:
    - "src/**"
  exclude:
    - "build/**"
  api_routes:
    enabled: false
''')
        
        config = load_bootstrap_config(tmp_path)
        assert config.include == ['src/**']
        assert config.exclude == ['build/**']
        assert config.api_routes_enabled is False
    
    def test_load_config_missing_file(self, tmp_path):
        """Should return default config if file missing."""
        config = load_bootstrap_config(tmp_path)
        assert config.include == ['**/*']
        assert '.git' in config.exclude
