# SPDX-FileCopyrightText: 2024 Alec Delaney
#
# SPDX-License-Identifier: MIT
#
# Based off of Makefile from circfirm: [https://github.com/tekktrik/circfirm]

.PHONY: lint
lint:
	@pre-commit run ruff --all-files

.PHONY: format
format:
	@pre-commit run ruff-format --all-files

.PHONY: check
check:
	@pre-commit run --all-files

.PHONY: test-prep
test-prep:
ifeq "$(OS)" "Windows_NT"
	-@mkdir testmount
	-@xcopy tests\assets\info_uf2.txt testmount
	-@subst T: testmount
else ifeq "$(shell uname -s)" "Linux"
	-@truncate testfs -s 1M
	-@mkfs.vfat -F12 -S512 testfs
	-@mkdir testmount
	-@sudo mount -o loop,user,umask=000 testfs testmount/
	-@cp tests/assets/info_uf2.txt testmount/
else ifeq "$(shell uname -s)" "Darwin"
	-@hdiutil create -size 512m -volname TESTMOUNT -fs FAT32 testfs.dmg
	-@hdiutil attach testfs.dmg
	-@cp tests/assets/info_uf2.txt /Volumes/TESTMOUNT
else
	@echo "Current OS not supported"
	@exit 1
endif
	-@git clone https://github.com/adafruit/circuitpython tests/sandbox/circuitpython --depth 1

.PHONY: test
test:
	-@${MAKE} test-prep --no-print-directory
	-@${MAKE} test-run --no-print-directory
	-@${MAKE} test-clean --no-print-directory

.PHONY:
test-run:
	@coverage run -m pytest
	-@coverage report
	-@coverage html

.PHONY: test-clean
test-clean:
ifeq "$(OS)" "Windows_NT"
	-@subst T: /d
	-@python scripts/rmdir.py testmount
	-@python scripts/rmdir.py tests/sandbox/circuitpython
else ifeq "$(shell uname -s)" "Linux"
	-@sudo umount testmount
	-@sudo rm -rf testmount
	-@rm testfs -f
	-@rm -rf tests/sandbox/circuitpython
else
	-@hdiutil detach /Volumes/TESTMOUNT
	-@rm testfs.dmg -f
	-@rm -rf tests/sandbox/circuitpython
endif
