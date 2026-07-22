# render/hansard_renderer.py

from typing import Any, Optional
import textwrap

# --- Utility Functions ---
def _render_section(title: str, content: list[str], detailed: bool) -> str:
    """Renders a generic section (e.g., 'Verdict' or 'Transcript')."""
    html = f'<section class="debate-section"><h2 class="section-title">{title}</h2><div class="content-wrapper">'
    if detailed and content:
        # Use collapsible structure for detailed transcripts
        html += '<details class="transcript-details"><h4>Full Debate Transcripts</h4>'
        html += '<p class="sr-only">Click to view full debate proceedings.</p>' # Screen reader description
        html += '<ul>'
        for item in content:
            # Assuming each item is a speaker block or paragraph chunk
            speaker_name, text = item[:2] if len(item) >= 2 else ("Unknown", item)
            safe_text = text.replace('"', '&quot;').replace('&', '&amp;')
            html += f'<li><strong>{speaker_name}</strong>: {safe_text}</li>'
        html += '</ul></div></details>'
    else:
        # Simple non-collapsible rendering for verdicts/key points
        content_list = "".join(f'<p>{item.strip()}</p>' for item in content)
        html += f'<div class="simple-content">{content_list}</div>'

    html += '</div></section>\n'
    return html


def render_html(hansard: Any, level: str = "full") -> str:
    """
    Generates a self-contained HTML string from the Hansard object.
    The resulting string includes all necessary CSS for portability.
    """

    # --- 1. Global Styles (Must be inline) ---
    CSS_STYLE = """
    <style>
        body { font-family: 'Georgia', serif; margin: 40px; background-color: #f9f9f9; color: #333; line-height: 1.6; }
        /* Main structure */
        #debate-export { max-width: 850px; margin: auto; padding: 30px; background: white; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); border-radius: 8px; }
        h1 { color: #1e3a5f; border-bottom: 2px solid #ccc; padding-bottom: 10px; margin-top: 0; }
        h2 { color: #475569; margin-top: 30px; border-left: 4px solid #b8c4d9; padding-left: 10px;}
        section { margin-bottom: 40px; padding: 15px; background-color: #ffffff; border: 1px solid #eee; border-radius: 6px; }

        /* Specific elements */
        .debate-metadata p { font-style: italic; color: #666; margin: 5px 0; }
        .question-box { background-color: #eef2ff; padding: 20px; border-left: 5px solid #3b82f6; margin-bottom: 30px; }
        .speaker-block, .verdict-point { margin-bottom: 15px; padding-left: 20px; border-left: 3px dashed #ddd; }
        .verdict-point strong { display: block; color: #ef4444; font-size: 1.1em; margin-bottom: 5px; }

        /* Transcripts (Collapsible) */
        details { border: 1px solid #ddd; padding: 10px; border-radius: 5px; background-color: #fafafa; margin-top: 10px; }
        summary { cursor: pointer; font-weight: bold; color: #3b82f6; outline: none; }
        .transcript-details ul { list-style-type: disc; padding-left: 25px; margin-top: 10px;}

        /* Accessibility */
        .sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); border: 0; }
    </style>
    """

    # --- 2. Core Rendering Logic ---

    html_parts = []

    # A. Metadata / Question
    q = hansard['question']
    metadata = f'''
    <div class="debate-metadata">
        <h1>{q['topic']}</h1>
        <p><strong>Date:</strong> {q['date'].strftime("%B %d, %Y")}</p>
        <p><strong>Motion:</strong> <em>"{q['motion']}"</em></p>
    </div>
    '''
    html_parts.append(metadata)

    # B. Speakers/Members
    speakers = hansard.get('speakers', [])
    speaker_content = []
    for speaker in speakers:
        speaker_block = f'''
        <div class="speaker-block">
            <h3>{speaker['name']}</h3>
            <p><em>Role: {speaker['role']}</em></p>
            <p>{speaker['speech'].replace('\n', '<br>')}</p>
        </div>
        '''
        speaker_content.append(speaker_block)

    html_parts.append('<section class="speakers"><h3>Speakers Present</h3>' + "".join(speaker_content) + '</section>')


    # C. Verdicts (Core Analysis)
    verdict = hansard.get('verdicts', {})
    verdict_parts = []

    if verdict:
        v_html = "<h3>Verdict and Disagreements</h3>"
        for part, points in verdict.items():
            v_title = part.capitalize() + " Verdict"
            points_list = [f'<strong>{p}</strong>: {text}' for p, text in points]
            verdict_parts.append(_render_section(v_title, points_list, detailed=False))

        html_parts.extend(verdict_parts)


    # D. Transcripts (Conditional Rendering)
    if level == 'full' and hansard.get('transcripts'):
        transcript_levels = hansard['transcripts']
        all_transcripts = []
        for speaker in transcript_levels:
             # Structure for full transcripts often includes multiple chunks/notes
            speaker_name, *speech_chunks = speaker
            full_text = "<br>".join([f"<strong>{chunk[0]}</strong>: {chunk[1]}" for chunk in speech_chunks])
            all_transcripts.append((speaker_name, full_text))

        html_parts.append(_render_section("Debate Transcripts", all_transcripts, detailed=True))


    # --- 3. Assembly ---
    final_content = "\n".join(html_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    {CSS_STYLE}
    <meta charset="UTF-8">
    <title>{hansard['question']['topic']} Debate</title>
</head>
<body>
    <div id="debate-export">
        <h1>[Export Generated by Parliament AI]</h1>
        {final_content}
    </div>
</body>
</html>"""

# End of render/hansard_renderer.py