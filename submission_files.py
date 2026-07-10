# Shared between app.py (author-side downloads) and editor.py (editor-side
# downloads) — kept out of both to avoid a circular import (app.py imports
# editor.py's blueprint at module load time).

FILE_FIELD_COLUMNS = {
    "manuscript": "manuscript_path",
    "graphical_abstract": "graphical_abstract_path",
    "cover_letter": "cover_letter_path",
    "supplementary": "supplementary_path",
}
