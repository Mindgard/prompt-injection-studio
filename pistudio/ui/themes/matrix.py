"""Matrix theme — green phosphor on black, digital rain inspired."""

from pistudio.ui.theme import Theme, build_logo, register_theme

_LOGO = build_logo(
    ("#00ff41", "#00ff41", "#00e639", "#00e639", "#00cc33", "#00cc33"),
    ("#00cc33", "#00cc33", "#00b32d", "#00b32d", "#009926", "#009926"),
)

register_theme(
    Theme(
        name="matrix",
        description="🟢  Matrix — green phosphor on black",
        accent="#00ff41",
        secondary="#00cc33",
        success="#00ff41",
        error="#ff0033",
        info="#00e639",
        warning="#b3ff00",
        muted="#3b8d3b",
        text="#00e639",
        border="#003300",
        toolbar_bg="#000000",
        toolbar_dim="#3b8d3b",
        toolbar_text="#00cc33",
        prompt_emojis=("⬢",),
        prompt_color="#00ff41",
        prompt_separator=">",
        prompt_separator_color="#558855",
        logo=_LOGO,
        subtitle_left="╌╌╌",
        subtitle_right="╌╌╌",
        goodbye_message="⬢ There is no spoon. Goodbye!",
        # Completion colors matching Matrix palette (all greens)
        completion_bg="#000000",  # Black
        completion_bg_selected="#2c2c2c",  # Slightly lighter for selection
        completion_command="#00ff41",  # Bright green (accent)
        completion_subcommand="#00cc33",  # Medium green (secondary)
        completion_flag="#b3ff00",  # Yellow-green (warning)
        completion_argument="#00e639",  # Green (info)
        completion_path="#00cc33",  # Medium green
        completion_meta="#66cc66",  # Brighter green for descriptions
        error_voice={
            "not_found": "{thing} '{name}': does not exist.",
            "usage": "{usage}",
            "failed": "{action}: {error}",
            "empty_prefix": "Empty.",
            "try_instead": "{suggestion}",
            "blocked": "DENIED. {reason}",
        },
    )
)
