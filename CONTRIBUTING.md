# Contributing to Terminal Agent

Thank you for your interest in contributing to **Terminal Agent**! An autonomous coding agent integrated deeply with the terminal, local testing, and Git version control.

Terminal Agent is maintained under the **PicadoLabs** organization ([https://github.com/PicadoLabs](https://github.com/PicadoLabs)).

---

## Table of Contents
1. [Code of Conduct](#code-of-conduct)
2. [Prerequisites](#prerequisites)
3. [Local Setup & Installation](#local-setup--installation)
4. [Testing & Quality Verification](#testing--quality-verification)
5. [Submitting Pull Requests](#submitting-pull-requests)

---

## 1. Code of Conduct
All contributors and maintainers are expected to adhere to the [Code of Conduct](CODE_OF_CONDUCT.md). Please report unacceptable behavior to [picadolabs@gmail.com](mailto:picadolabs@gmail.com).

## 2. Prerequisites
- Python 3.10+
- Git 2.30+

## 3. Local Setup & Installation
1. Clone the repo.
2. `cd Terminal Agent`
3. `pip install -e .[dev,test]`

## 4. Testing & Quality Verification
Before submitting a pull request, ensure all tests pass:
`pytest tests/ -v`

## 5. Submitting Pull Requests
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/my-new-feature`).
3. Commit your changes (`git commit -am 'Add some feature'`).
4. Push to the branch (`git push origin feature/my-new-feature`).
5. Create a new Pull Request.
