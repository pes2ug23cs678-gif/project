import re
def chunk_by_procedure(text):
    sections = re.split(r'\n([A-Z0-9\-]+\.)', text)
    chunks = []
    for i in range(1, len(sections), 2):
        # Combine the header ('UPDATE-LOGIC.') with body content
        chunk = sections[i] + sections[i+1]
        chunks.append(chunk.strip())
	# If no sections found, return the whole text as one chunk
        return chunks if chunks else [text]
