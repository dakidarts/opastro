from __future__ import annotations

from setuptools import setup
from setuptools.command.sdist import sdist as _sdist


_SDIST_EXCLUDE_PREFIXES = (
    "tests/",
    "docs/tasks/",
    "scripts/",
)

_SDIST_EXCLUDE_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".DS_Store",
)


class OpastroSdist(_sdist):
    def get_file_list(self) -> None:
        super().get_file_list()
        self.filelist.files = [
            path
            for path in self.filelist.files
            if not path.startswith(_SDIST_EXCLUDE_PREFIXES) and not path.endswith(_SDIST_EXCLUDE_SUFFIXES)
        ]

    def make_release_tree(self, base_dir: str, files: list[str]) -> None:
        filtered = [
            path
            for path in files
            if not path.startswith(_SDIST_EXCLUDE_PREFIXES) and not path.endswith(_SDIST_EXCLUDE_SUFFIXES)
        ]
        super().make_release_tree(base_dir, filtered)

if __name__ == "__main__":
    setup(cmdclass={"sdist": OpastroSdist})
