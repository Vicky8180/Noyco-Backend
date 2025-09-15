"""
Documentation Router
Serves markdown documentation files for microservices
"""

from fastapi import APIRouter, HTTPException, Response
from pathlib import Path
import os
import re
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/docs", tags=["Documentation"])

# Get the documentation directory path
DOC_DIR = Path(__file__).parent.parent.parent / "doc"

def sanitize_path_part(part: str) -> str:
    """Sanitize a single path part to prevent path traversal attacks"""
    # URL decode the part first
    import urllib.parse
    decoded_part = urllib.parse.unquote(part)
    
    # Remove any path separators and dangerous characters, but keep spaces and common filename chars
    sanitized = re.sub(r'[<>:"|?*\x00-\x1f]', '', decoded_part)
    # Remove any attempts at path traversal
    sanitized = sanitized.replace('..', '').replace('/', '').replace('\\', '')
    return sanitized.strip()

def get_doc_files() -> List[Dict[str, Any]]:
    """Get list of all markdown files in the doc directory with folder structure"""
    if not DOC_DIR.exists():
        return []
    
    docs = []
    for file_path in DOC_DIR.rglob("*.md"):
        relative_path = file_path.relative_to(DOC_DIR)
        
        # Extract folder structure
        path_parts = list(relative_path.parts)
        folder_path = str(relative_path.parent) if relative_path.parent != Path('.') else ''
        
        docs.append({
            "name": file_path.stem,
            "filename": file_path.name,
            "path": str(relative_path).replace("\\", "/"),
            "folder": folder_path.replace("\\", "/") if folder_path else "",
            "size": file_path.stat().st_size,
            "modified": file_path.stat().st_mtime,
            "category": _determine_category(file_path.stem),
            "full_path": str(file_path)
        })
    
    return sorted(docs, key=lambda x: (x["folder"], x["name"]))

def _determine_category(filename: str) -> str:
    """Determine category based on filename patterns"""
    filename_lower = filename.lower()
    
    if any(keyword in filename_lower for keyword in ['guide', 'documentation', 'readme']):
        return 'Guides'
    elif any(keyword in filename_lower for keyword in ['service', 'auth', 'billing']):
        return 'Services'
    elif any(keyword in filename_lower for keyword in ['api', 'gateway', 'endpoint']):
        return 'API Documentation'
    elif any(keyword in filename_lower for keyword in ['getting', 'start', 'intro', 'setup']):
        return 'Getting Started'
    else:
        return 'Other'

def find_file_by_name(filename: str) -> Path:
    """
    Find a markdown file by name, searching recursively through all subdirectories
    
    Args:
        filename: The filename to search for (with or without .md extension)
    
    Returns:
        Path to the found file
        
    Raises:
        HTTPException: If file is not found
    """
    if not DOC_DIR.exists():
        raise HTTPException(status_code=404, detail="Documentation directory not found")
    
    # Ensure .md extension
    if not filename.endswith('.md'):
        filename += '.md'
    
    # Search for the file recursively
    for file_path in DOC_DIR.rglob(filename):
        return file_path
    
    # If not found by exact filename, try searching by stem (filename without extension)
    search_stem = filename[:-3] if filename.endswith('.md') else filename
    for file_path in DOC_DIR.rglob("*.md"):
        if file_path.stem == search_stem:
            return file_path
    
    raise HTTPException(
        status_code=404, 
        detail=f"Documentation file '{filename}' not found in any directory"
    )

@router.get("/")
async def list_documentation():
    """
    List all available documentation files
    
    Returns a list of all markdown files in the doc directory with metadata
    """
    try:
        docs = get_doc_files()
        return {
            "status": "success",
            "total_docs": len(docs),
            "documentation": docs,
            "endpoints": {
                "get_doc": "/docs/{filename}",
                "get_raw": "/docs/raw/{filename}",
                "list_all": "/docs/"
            }
        }
    except Exception as e:
        logger.error(f"Error listing documentation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list documentation")

@router.get("/{file_path:path}")
async def get_documentation(file_path: str):
    """
    Get documentation content as JSON with metadata
    
    Args:
        file_path: Path to the markdown file (can include folders)
    
    Returns:
        JSON response with documentation content and metadata
    """
    try:
        # Handle nested paths and sanitize
        path_parts = [sanitize_path_part(part) for part in file_path.split('/')]
        clean_path = '/'.join(path_parts)
        
        # Ensure .md extension
        if not clean_path.endswith('.md'):
            clean_path += '.md'
        
        file_path_obj = DOC_DIR / clean_path
        
        # Check if file exists at the direct path
        if not file_path_obj.exists():
            # If direct path fails, try to find the file by name
            try:
                file_path_obj = find_file_by_name(path_parts[-1])  # Use the last part as filename
                # Update clean_path to reflect the actual path found
                clean_path = str(file_path_obj.relative_to(DOC_DIR)).replace("\\", "/")
            except HTTPException:
                # If both direct path and name search fail, raise original error
                raise HTTPException(
                    status_code=404, 
                    detail=f"Documentation file '{clean_path}' not found"
                )
        
        # Read file content
        with open(file_path_obj, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Get file metadata
        stat = file_path_obj.stat()
        
        return {
            "status": "success",
            "filename": file_path_obj.name,
            "path": clean_path,
            "content": content,
            "metadata": {
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "lines": len(content.splitlines())
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading documentation file '{clean_path}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to read documentation file")

@router.get("/raw/{file_path:path}")
async def get_raw_documentation(file_path: str):
    """
    Get raw markdown content with appropriate content-type header
    
    Args:
        file_path: Path to the markdown file (can include folders)
    
    Returns:
        Raw markdown content with text/markdown content-type
    """
    try:
        # Handle nested paths and sanitize
        path_parts = [sanitize_path_part(part) for part in file_path.split('/')]
        clean_path = '/'.join(path_parts)
        
        # Ensure .md extension
        if not clean_path.endswith('.md'):
            clean_path += '.md'
        
        file_path_obj = DOC_DIR / clean_path
        
        # Check if file exists at the direct path
        if not file_path_obj.exists():
            # If direct path fails, try to find the file by name
            try:
                file_path_obj = find_file_by_name(path_parts[-1])  # Use the last part as filename
            except HTTPException:
                # If both direct path and name search fail, raise original error
                raise HTTPException(
                    status_code=404, 
                    detail=f"Documentation file '{clean_path}' not found"
                )
        
        # Read file content
        with open(file_path_obj, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return Response(
            content=content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"inline; filename={file_path_obj.name}",
                "Cache-Control": "public, max-age=3600"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading raw documentation file '{clean_path}': {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to read documentation file")

@router.get("/search/{query}")
async def search_documentation(query: str):
    """
    Search through documentation files for content
    
    Args:
        query: Search term to look for in documentation
    
    Returns:
        List of matching documents with highlighted content
    """
    try:
        if len(query.strip()) < 2:
            raise HTTPException(status_code=400, detail="Search query must be at least 2 characters")
        
        query_lower = query.lower()
        results = []
        
        for file_path in DOC_DIR.rglob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if query_lower in content.lower():
                    # Find matching lines
                    lines = content.splitlines()
                    matching_lines = []
                    
                    for i, line in enumerate(lines):
                        if query_lower in line.lower():
                            matching_lines.append({
                                "line_number": i + 1,
                                "content": line.strip()
                            })
                    
                    relative_path = file_path.relative_to(DOC_DIR)
                    results.append({
                        "filename": file_path.name,
                        "path": str(relative_path).replace("\\", "/"),
                        "matches": len(matching_lines),
                        "matching_lines": matching_lines[:5]  # Limit to first 5 matches
                    })
            
            except Exception as e:
                logger.warning(f"Error searching in file {file_path}: {str(e)}")
                continue
        
        return {
            "status": "success",
            "query": query,
            "total_matches": len(results),
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching documentation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to search documentation")