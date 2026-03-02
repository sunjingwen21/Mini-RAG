import traceback
import sys
import uuid
from app.rag import rag_engine, Document

try:
    doc = Document(
        id=f"debug_{uuid.uuid4().hex}",
        title='Test',
        content='Searching for test text',
        tags=['debug']
    )
    rag_engine.index_document(doc)
    
    print("Document Indexed. Running search...")
    res = rag_engine.search('test text', limit=5)
    print("Search Result:", res)
except Exception as e:
    print("Error during Chroma Query:")
    traceback.print_exc()
finally:
    try:
        rag_engine.remove_document(doc.id)
    except Exception:
        pass
