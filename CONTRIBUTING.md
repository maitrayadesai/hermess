# Contributing to HERMESS

Thank you for your interest in contributing. Bug reports, questions and pull
requests are welcome through the GitHub issue tracker and pull requests.

## Development setup

```bash
git clone https://github.com/maitrayadesai/hermess
cd hermess
uv sync            # or: pip install -e . && pip install pytest pytest-cov
uv run pytest -q   # run the test suite
```

Code is formatted with `black` and linted with `flake8` (see
`.pre-commit-config.yaml`). Run `pre-commit install` once to enable the hooks.

## Guidelines

- Open an issue first for larger changes so the design can be discussed.
- Keep the simulation baselines in `hermess/tests/baselines/` and the fixtures
  in `hermess/tests/fixtures/` unchanged unless the change is intentional and
  explained in the pull request.
- Add or update tests for any behavioral change.
- New source files should carry the same copyright and license header as the
  existing ones.

## Licensing of contributions

HERMESS is released under the GNU General Public License v3.0 or later
(see `LICENSE.txt`). By submitting a contribution you confirm that you have the
right to do so and you agree that your contribution is licensed under the same
license as the project. No contributor license agreement is required.

Contributors are credited in `CONTRIBUTORS`; please add yourself in your pull
request if you wish.

## Contact

Maitraya Avadhut Desai, mdesai@ethz.ch
