push:
	git add . && git commit -m "up" . && git push

.PHONY: apm-up apm-down apm-ps apm-logs apm-validate apm-test apm-contract

apm-up:
	$(MAKE) -C deploy/apm up

apm-down:
	$(MAKE) -C deploy/apm down

apm-ps:
	$(MAKE) -C deploy/apm ps

apm-logs:
	$(MAKE) -C deploy/apm logs

apm-validate:
	$(MAKE) -C deploy/apm validate

apm-test:
	$(MAKE) -C deploy/apm test

apm-contract:
	$(MAKE) -C deploy/apm contract
