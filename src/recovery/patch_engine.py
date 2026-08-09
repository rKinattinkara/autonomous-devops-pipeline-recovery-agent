def apply_simple_patch(
    current_content: str,
    patch: str,
) -> str:

    removed_lines = []
    added_lines = []
    context_before = []
    context_after = []
    found_removed = False

    for line in patch.splitlines():

        if line.startswith("---") or line.startswith("+++"):
            continue

        if line.startswith("@@"):
            continue

        if line.startswith("-"):
            removed_lines.append(line[1:])
            found_removed = True

        elif line.startswith("+"):
            added_lines.append(line[1:])

        else:
            ctx_line = line[1:] if line.startswith(" ") else line
            if not found_removed:
                context_before.append(ctx_line)
            else:
                context_after.append(ctx_line)

    if not removed_lines and not added_lines:
        raise ValueError("Patch contains no changes.")

    nl = "\n"
    old_block = nl.join(context_before + removed_lines + context_after)
    new_block = nl.join(context_before + added_lines + context_after)

    if old_block not in current_content:
        raise ValueError(
            "Expected source block was not found in the target file."
        )

    if current_content.count(old_block) != 1:
        raise ValueError(
            "Patch target is ambiguous — it occurs multiple times. "
            "Provide a more specific patch hunk with more context."
        )

    return current_content.replace(old_block, new_block, 1)
