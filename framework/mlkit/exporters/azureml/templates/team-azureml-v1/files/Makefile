# Inert by design (Hypotrail export): these targets print the commands of this project.
# They never edit ~/.bashrc, ~/.zshrc or the `cd` command, unlike the original template.
.ONESHELL:

###############################################################
# VARIABLES                                                   #
###############################################################
PROJECT_CONFIG_FILE=cli-aliases.sh

###############################################################
# Project commands (printed, not installed in your shell)     #
###############################################################
.PHONY: bash
bash:
	@echo "Nothing is added to your shell. To load the reminders in this terminal only:"
	@echo "  source $(PROJECT_CONFIG_FILE)"

.PHONY: unbash
unbash:
	@echo "Nothing to remove: 'make bash' never edits your shell configuration."

.PHONY: help
help:
	@echo "python -m src.pipeline.utils.project validate --offline"
	@echo "python -m src.pipeline.utils.project run-local --mode rebuild_final_candidate"
	@echo "python -m src.pipeline.utils.project preflight"
