# 1. Use the exact Ubuntu operating system that Google Colab uses
FROM ubuntu:22.04

# 2. Stop the server from asking yes/no questions during installation
ENV DEBIAN_FRONTEND=noninteractive

# 3. Download Python and Tesseract directly from the Ubuntu archives
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# 4. Create a folder for our app
WORKDIR /app

# 5. Copy your requirements file and install the Python libraries
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# 6. Copy all your code into the app folder
COPY . .

# 7. Tell Railway how to launch the Streamlit app
CMD streamlit run app.py --server.port $PORT --server.address 0.0.0.0
