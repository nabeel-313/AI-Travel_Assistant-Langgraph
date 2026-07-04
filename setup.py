import tomli
from setuptools import setup, find_packages

# Read dependencies from pyproject.toml
with open("pyproject.toml", "rb") as f:
    pyproject_data = tomli.load(f)

install_requires = pyproject_data["project"]["dependencies"]
extras_require = pyproject_data["project"].get("optional-dependencies", {})

setup(
    name=pyproject_data["project"]["name"],
    version=pyproject_data["project"]["version"],
    author=pyproject_data["project"]["authors"][0]["name"],
    author_email=pyproject_data["project"]["authors"][0]["email"],
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=install_requires,
    extras_require=extras_require,
    python_requires=pyproject_data["project"]["requires-python"],
)
