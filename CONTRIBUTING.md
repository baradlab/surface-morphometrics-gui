# Contributing to Surface Morphometrics GUI

Thank you for your interest in contributing to the Surface Morphometrics GUI project! Your help is valued and will make this tool better for the research community.

## Table of Contents
- [Project Scope](#project-scope)
- [Getting Started](#getting-started)
- [Development Guidelines](#development-guidelines)
- [Code Style](#code-style)
- [Testing](#testing)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)
- [Pull Request Process](#pull-request-process)
- [Contact](#contact)

## Project Scope
This repository provides a napari-based GUI for analyzing and quantifying membrane ultrastructure in cryo-electron tomography data, built on the [surface morphometrics pipeline](https://github.com/GrotjahnLab/surface_morphometrics).

## Getting Started
To set up your development environment:

1. **Install the upstream surface morphometrics pipeline**
   - Follow the instructions at [GrotjahnLab/surface_morphometrics](https://github.com/GrotjahnLab/surface_morphometrics) to set up the base pipeline and its conda environment (usually named `morphometrics`).

2. **Clone this repository**
   ```bash
   git clone https://github.com/baradlab/surface-morphometrics-gui.git
   cd surface-morphometrics-gui
   ```

3. **Activate the conda environment**
   ```bash
   conda activate morphometrics
   ```

4. **Install additional dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the GUI**
   ```bash
   python main.py
   ```

If you encounter issues, please open an issue or reach out for help.

## Development Guidelines
- Write clear, concise, and well-documented code.
- Follow the existing project structure and naming conventions.
- Add or update docstrings for all public functions, classes, and modules.
- Ensure your changes do not break existing functionality.
- If your contribution changes the UI, please include before/after screenshots.
- When adding new dependencies, update the documentation and requirements as needed.

## Code Style
- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code.
- Use consistent indentation (4 spaces).
- Use descriptive variable and function names.
- Keep imports organized and remove unused imports.

## Testing
- Add tests for new features and bug fixes when possible.
- If adding new modules, consider including a corresponding test file.

## Reporting Bugs
If you find a bug:
1. Search [existing issues](https://github.com/baradlab/surface-morphometrics-gui/issues) to see if it has already been reported.
2. If not, open a new issue and include:
   - A clear description of the problem
   - Steps to reproduce
   - Expected and actual behavior
   - Screenshots or logs if applicable

## Requesting Features
To request a new feature:
1. Search [existing issues](https://github.com/baradlab/surface-morphometrics-gui/issues) for similar requests.
2. If not found, open a new issue and describe:
   - The motivation for the feature
   - How it would be used
   - Any relevant context or examples

## Pull Request Process
1. Fork the repository and create your branch from `main` (or the relevant feature branch):
   ```bash
   git checkout -b my-feature
   ```
2. Make your changes and commit them with clear messages.
3. Push your branch to your fork and open a pull request.
4. Ensure your PR:
   - References related issues (if any)
   - Includes documentation and tests as appropriate
5. Participate in the review process and address feedback promptly.

## Contact
For questions, support, or to discuss larger contributions, please open an issue or contact the maintainers via the Issues page on GitHub.

---
Thank you for helping make Surface Morphometrics GUI better for everyone!

