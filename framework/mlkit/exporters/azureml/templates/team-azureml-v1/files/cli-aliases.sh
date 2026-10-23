# Inert by design (Hypotrail export). Sourcing this file in a terminal defines shell
# functions that print or run this project's commands. It reads no .env file, edits no
# shell configuration, creates or removes no conda environment and deletes nothing.

PROJECT_NAME=$(basename "$PWD")

# Print the commands of the project
project_help() {
    echo "python -m src.pipeline.utils.project validate --offline"
    echo "python -m src.pipeline.utils.project predict --input FILE --output FILE"
    echo "python -m src.pipeline.utils.project run-local --mode rebuild_final_candidate"
    echo "python -m src.pipeline.utils.project preflight"
    echo "python -m src.pipeline.utils.project submit"
}

# The environment commands, printed for $PROJECT_NAME (run them yourself)
envc() {
    echo "conda env create -f environment.yml -n $PROJECT_NAME"
}

enva() {
    echo "conda activate $PROJECT_NAME"
}

quality() {
    ruff check src
}

tests() {
    pytest
}
