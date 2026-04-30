import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class RepoIntelligence:
    """Interface for GitNexus code intelligence."""
    
    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir)

    def analyze(self) -> str:
        """Run gitnexus analyze to index the repository."""
        try:
            # Run npx gitnexus analyze
            result = subprocess.run(
                ["npx", "-y", "gitnexus@latest", "analyze"],
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(f"GitNexus analysis failed: {e.stderr}")
            return f"Error: {e.stderr}"
        except FileNotFoundError:
            return "Error: npx or gitnexus not found. Please install Node.js."

    def get_context(self) -> str:
        """Read the generated context files (AGENTS.md or CLAUDE.md)."""
        agents_md = self.project_dir / "AGENTS.md"
        claude_md = self.project_dir / "CLAUDE.md"
        
        context = ""
        if agents_md.exists():
            context += f"\n### Project Structure (AGENTS.md):\n{agents_md.read_text()}\n"
        elif claude_md.exists():
            context += f"\n### Project Context (CLAUDE.md):\n{claude_md.read_text()}\n"
            
        return context
