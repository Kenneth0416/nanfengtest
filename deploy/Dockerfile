# London Office Market Agent: Python app + Node 22 for the Pi Durable agent engine, in one image.
#   docker compose up            (from the repository root; see README "Try it in three steps")
FROM python:3.13-slim

# Node 22 for Pi Durable; poppler for PDF page images (uploaded reports, lease photos, slide previews);
# LibreOffice Impress renders the built deck to PDF for the slide preview and Writer the research note; Carlito and
# Caladea stand in for Calibri and Cambria at the same widths; curl for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg poppler-utils \
    libreoffice-impress libreoffice-writer fonts-dejavu-core fonts-crosextra-carlito fonts-crosextra-caladea \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pi_engine/package*.json pi_engine/
RUN cd pi_engine && npm ci --omit=dev
COPY . .
RUN useradd -m app && mkdir -p /app/data && chown -R app /app
USER app
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD curl -fs http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
