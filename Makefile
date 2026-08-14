.PHONY: test deep scan

check:
	@pnpm audit
	@pnpm prettier
	@pnpm lint
	@pre-commit run --all-files

fix:
	@pnpm prettier-fix
	@pnpm lint-fix

audit-fix:
	@pnpm audit --fix override

install:
	@pnpm install --frozen-lockfile

test:
	@pnpm test
