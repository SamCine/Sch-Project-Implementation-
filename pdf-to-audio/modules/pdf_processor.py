"""
PDF Processor Module
Extracts text, pages, and chapters from PDF files using PyMuPDF (fitz).
"""

import fitz  # PyMuPDF
import pdfplumber
import re
import os


class PDFProcessor:
    def __init__(self, filepath):
        self.filepath = filepath
        self.doc = fitz.open(filepath)
        self.total_pages = len(self.doc)

    def close(self):
        self.doc.close()

    def get_metadata(self):
        """Return PDF metadata."""
        meta = self.doc.metadata
        return {
            "title": meta.get("title", os.path.basename(self.filepath)),
            "author": meta.get("author", "Unknown"),
            "total_pages": self.total_pages,
            "subject": meta.get("subject", ""),
        }

    def extract_page_text(self, page_num):
        """Extract text from a specific page (0-indexed)."""
        if page_num < 0 or page_num >= self.total_pages:
            return ""
        page = self.doc[page_num]
        text = page.get_text("text")
        return self._clean_text(text)

    def extract_all_text(self):
        """Extract all text from the PDF."""
        full_text = []
        for i in range(self.total_pages):
            text = self.extract_page_text(i)
            if text.strip():
                full_text.append(text)
        return "\n\n".join(full_text)

    def extract_pages_range(self, start_page, end_page):
        """Extract text from a range of pages (1-indexed for user-facing)."""
        start = max(0, start_page - 1)
        end = min(self.total_pages, end_page)
        texts = []
        for i in range(start, end):
            text = self.extract_page_text(i)
            if text.strip():
                texts.append(f"Page {i+1}.\n{text}")
        return "\n\n".join(texts)

    def detect_chapters(self):
        """
        Detect chapters/sections from the PDF using TOC or heuristic heading detection.
        Returns list of dicts: [{title, page, text}]
        """
        chapters = []

        # Try TOC first (most reliable)
        toc = self.doc.get_toc()
        if toc:
            for i, entry in enumerate(toc):
                level, title, page = entry
                if level == 1:  # Only top-level chapters
                    start_page = page
                    end_page = toc[i + 1][2] if i + 1 < len(toc) else self.total_pages
                    text = self.extract_pages_range(start_page, end_page - 1)
                    chapters.append({
                        "title": title.strip(),
                        "start_page": start_page,
                        "end_page": end_page - 1,
                        "text": text
                    })

        # Fallback: heuristic heading detection
        if not chapters:
            chapters = self._detect_chapters_heuristic()

        # Fallback: page-by-page if nothing found
        if not chapters:
            chapters = self._split_by_pages()

        return chapters

    def _detect_chapters_heuristic(self):
        """Detect chapters using text pattern heuristics.
        Only matches real chapter/section headings — not numbered list items.
        """
        chapters = []
        # Strict pattern: must be a standalone heading like "Chapter 1", "Section 2", "PART III"
        # NOT "1. Do something..." (that's a list item)
        chapter_pattern = re.compile(
            r'^(chapter\s+[\divxlcdm]+|section\s+[\divxlcdm\d]+|part\s+[ivxlcdm\d]+)[\s:\-—]*',
            re.IGNORECASE
        )

        current_chapter = None
        current_text = []
        current_start = 1

        for i in range(self.total_pages):
            page_text = self.extract_page_text(i)
            lines = page_text.split('\n')

            matched = False
            for line in lines[:5]:  # Check first 5 lines of each page
                stripped = line.strip()
                # Must be short, standalone heading — not a sentence or list item
                if (stripped
                        and chapter_pattern.match(stripped)
                        and len(stripped) < 60
                        and not stripped[0].isdigit()):   # exclude "1. blah" list items
                    if current_chapter and current_text:
                        chapters.append({
                            "title":      current_chapter,
                            "start_page": current_start,
                            "end_page":   i,
                            "text":       "\n".join(current_text)
                        })
                    current_chapter = stripped
                    current_text = [page_text]
                    current_start = i + 1
                    matched = True
                    break

            if not matched:
                current_text.append(page_text)

        # Append last chapter
        if current_chapter and current_text:
            chapters.append({
                "title":      current_chapter,
                "start_page": current_start,
                "end_page":   self.total_pages,
                "text":       "\n".join(current_text)
            })

        return chapters

    def _split_by_pages(self):
        """Split into page-by-page chapters as last resort."""
        chapters = []
        pages_per_chunk = max(1, self.total_pages // 10)  # ~10 chunks

        for i in range(0, self.total_pages, pages_per_chunk):
            end = min(i + pages_per_chunk, self.total_pages)
            text = self.extract_pages_range(i + 1, end)
            if text.strip():
                chapters.append({
                    "title": f"Pages {i+1}–{end}",
                    "start_page": i + 1,
                    "end_page": end,
                    "text": text
                })

        return chapters

    def _clean_text(self, text):
        """Clean extracted text for better TTS output."""
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)

        # Remove page numbers (standalone numbers on a line)
        text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)

        # Remove headers/footers (very short lines that repeat)
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            stripped = line.strip()
            # Skip very short non-sentence lines that look like headers
            if len(stripped) > 0:
                cleaned.append(stripped)

        return '\n'.join(cleaned).strip()

    def get_page_count(self):
        return self.total_pages
