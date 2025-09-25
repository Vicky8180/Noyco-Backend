#!/usr/bin/env python3
"""
Service-Specific Dependency Analysis Script
Analyzes and compares requirements for core, agents, and memory services
"""

import os
from pathlib import Path
from collections import defaultdict


def count_packages_in_requirements(file_path):
    """Count packages in a requirements file"""
    if not os.path.exists(file_path):
        return 0, []
    
    packages = []
    try:
        # Try different encodings to handle files with BOM or encoding issues
        encodings = ['utf-16', 'utf-16-le', 'utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        content = None
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            print(f"Warning: Could not read {file_path} with any encoding")
            return 0, []
        
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and '==' in line:
                package_name = line.split('==')[0].strip()
                packages.append(line)
    
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return 0, []
    
    return len(packages), packages


def analyze_all_requirements():
    """Analyze all requirements files"""
    print("📊 Service-Specific Requirements Analysis")
    print("=" * 60)
    
    requirements_files = {
        "Main Project": "requirements3.txt",
        "API Gateway": "api_gateway/requirements.txt",
        "Core Service": "core/requirements.txt", 
        "Agents Service": "specialists/agents/requirements.txt",
        "Memory Service": "memory/requirements.txt"
    }
    
    results = {}
    
    for service_name, file_path in requirements_files.items():
        count, packages = count_packages_in_requirements(file_path)
        results[service_name] = {
            'count': count,
            'packages': packages,
            'file_path': file_path
        }
        
        status = "✅" if count > 0 else "❌"
        print(f"{status} {service_name:<15} {count:>3} packages ({file_path})")
    
    print("\n" + "=" * 60)
    
    # Calculate reductions
    main_count = results["Main Project"]["count"]
    if main_count > 0:
        print(f"\n📉 Dependency Reduction Analysis:")
        print(f"   Main Project Base: {main_count} packages")
        
        for service_name in ["API Gateway", "Core Service", "Agents Service", "Memory Service"]:
            if service_name in results:
                service_count = results[service_name]["count"]
                if service_count > 0:
                    reduction = main_count - service_count
                    percentage = (reduction / main_count) * 100
                    print(f"   {service_name:<15}: {service_count:>3} packages (-{reduction:>3} = {percentage:>5.1f}% reduction)")
    
    # Show package breakdown
    print(f"\n📦 Package Breakdown by Service:")
    print("-" * 40)
    
    for service_name in ["API Gateway", "Core Service", "Agents Service", "Memory Service"]:
        if service_name in results and results[service_name]["count"] > 0:
            print(f"\n{service_name}:")
            for package in results[service_name]["packages"]:
                print(f"  - {package}")
    
    return results


def create_consolidated_install_guide():
    """Create installation guide for different deployment scenarios"""
    guide = """
# Service Installation Guide

## Individual Service Installation

### API Gateway Only
```bash
cd api_gateway/
pip install -r requirements.txt
```

### Core Service Only
```bash
cd core/
pip install -r requirements.txt
```

### Agents Service Only  
```bash
cd specialists/agents/
pip install -r requirements.txt
```

### Memory Service Only
```bash
cd memory/
pip install -r requirements.txt
```

## Combined Installations

### API Gateway + Core (Common setup)
```bash
pip install -r api_gateway/requirements.txt
pip install -r core/requirements.txt
```

### Core + Agents (Common for most deployments)
```bash
pip install -r core/requirements.txt
pip install -r specialists/agents/requirements.txt
```

### Full Platform (All Services)
```bash
pip install -r requirements3.txt
```

## Docker/Container Optimization

### Multi-stage Dockerfile example for API Gateway:
```dockerfile
FROM python:3.11-slim as api-gateway
WORKDIR /app
COPY api_gateway/requirements.txt .
RUN pip install -r requirements.txt
COPY api_gateway/ ./api_gateway/
COPY common/ ./common/
CMD ["uvicorn", "api_gateway.main:socket_app", "--host", "0.0.0.0", "--port", "8001"]
```

### Multi-stage Dockerfile example for Core Service:
```dockerfile
FROM python:3.11-slim as core-service
WORKDIR /app
COPY core/requirements.txt .
RUN pip install -r requirements.txt
COPY core/ ./core/
COPY common/ ./common/
CMD ["uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

### Multi-stage Dockerfile example for Agents Service:
```dockerfile
FROM python:3.11-slim as agents-service
WORKDIR /app
COPY specialists/agents/requirements.txt .
RUN pip install -r requirements.txt
COPY specialists/agents/ ./specialists/agents/
CMD ["uvicorn", "specialists.agents.main:app", "--host", "0.0.0.0", "--port", "8015"]
```
"""
    
    with open("SERVICE_INSTALLATION_GUIDE.md", "w") as f:
        f.write(guide)
    
    print("📝 Created SERVICE_INSTALLATION_GUIDE.md")


def main():
    """Main analysis function"""
    os.chdir(Path(__file__).parent)
    
    # Analyze requirements
    results = analyze_all_requirements()
    
    # Create installation guide
    create_consolidated_install_guide()
    
    print(f"\n✅ Analysis complete!")
    print(f"   Each service now has its own minimal requirements.txt")
    print(f"   Check the SERVICE_INSTALLATION_GUIDE.md for deployment options")


if __name__ == "__main__":
    main()