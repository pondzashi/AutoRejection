# -*- coding: utf-8 -*-
import csv
import glob
import json
import re
import multiprocessing as mp
import os
import shutil
from datetime import datetime
from itertools import islice
from charset_normalizer import from_path

#library to get argument from cmd
import argparse

# สร้าง Argument Parser
parser = argparse.ArgumentParser(description="Process input and output files.")
parser.add_argument("conf_root_path", help="Path to the general config file")  # พารามิเตอร์แรก (จำเป็น)
parser.add_argument("conf_pack_path", help="Path to the pack config file")  # พารามิเตอร์ที่สอง (จำเป็น)

# แปลง Argument เป็นค่าที่ Python ใช้งานได้
args = parser.parse_args()


# =========================
# Encoding Service
# =========================
class EncodingService:
    @staticmethod
    def detect(file_path):
        result = from_path(file_path).best()
        return result.encoding if result else "utf-8"


# =========================
# Config Loader
# =========================
class ConfigLoader:
    def __init__(self, root_path, pack_path):
        self.root_path = root_path
        self.pack_path = pack_path

    def load(self):
        with open(self.root_path, encoding="utf-8") as f:
            config = json.load(f)

        config["meta"] = []
        for file in glob.glob(self.pack_path):
            with open(file, encoding="utf-8") as f:
                config["meta"].append(json.load(f))

        return config


# =========================
# Validator
# =========================
class Validator:
    NUMERIC_REGEX = re.compile(r"^-?\d+(\.\d+)?$")

    def __init__(self, columns_config, header_row):
        self.columns_config = columns_config
        self.expected_columns = len(columns_config)
        self.header_row = header_row

        # compile date regex once
        self.date_patterns = {
            k: re.compile(v.get("date_format"))
            for k, v in columns_config.items()
            if v.get("date_format")
        }

    def validate_row(self, row, row_number):
        errors = []

        if len(row) != self.expected_columns:
            return [f"Row {row_number},Column count mismatch: {len(row)}"]

        for i, val in enumerate(row):
            cfg = self.columns_config.get(str(i), {})
            col_name = cfg.get("name", "")
            max_len = cfg.get("max_length", 9999)
            col_type = cfg.get("type")
            date_format = cfg.get("date_format","^^([0-2][0-9]|3[01])-(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-\\d{4} ([01]\\d|2[0-3]):[0-5]\\d:[0-5]\\d$")
            DATE_REGEX = re.compile(rf"{date_format}")

        if row_number != self.header_row:
            if len(val) > max_len:
                errors.append(f"Row {row_number}, Column {col_name} length overflow ({len(val)})")
            if col_type == "numeric":  
                if val != "" and not self.NUMERIC_REGEX.match(val):
                    errors.append(f"Row {row_number}, Column {col_name} not numeric: {val}")
            if col_type == "date": 
                if val != "" and not DATE_REGEX.match(val):
                    errors.append(f"Row {row_number}, Column {col_name} invalid date format: {val}")

        return errors

    def process_chunk(self, chunk, start_row):
        valid, errors = [], []
        error_count = 0

        for i, row in enumerate(chunk):
            row_number = start_row + i
            row = [c.strip() for c in row]

            err = self.validate_row(row, row_number)
            if err:
                errors.append(["Errors: " + "; ".join(err)] + row)
                error_count += 1
            else:
                valid.append(row)

        return valid, errors, error_count, len(chunk)


# =========================
# Chunk Reader
# =========================
class ChunkReader:
    def __init__(self, file_path, col_delimiter, chunk_size, encoding):
        self.file_path = file_path
        self.col_delimiter = col_delimiter
        self.chunk_size = chunk_size
        self.encoding = encoding

    def __iter__(self):
        try:
            with open(self.file_path, encoding=self.encoding) as f:
                reader = csv.reader(f, delimiter=self.col_delimiter,quoting=csv.QUOTE_NONE)
                row_number = 1
                while True:
                    chunk = list(islice(reader, self.chunk_size))
                    if not chunk:
                        break

                    yield chunk, row_number
                    row_number += len(chunk)
        except FileNotFoundError:
            print(f"Error: File {self.file_path} not found.")
            exit(1)

# =========================
# Writer Process
# =========================
class Writer:
    def __init__(self, queue, output_file, col_delimiter,row_delimiter, encoding):
        self.queue = queue
        self.output_file = output_file
        self.col_delimiter = col_delimiter
        self.row_delimiter = row_delimiter        
        self.encoding = encoding

    def run(self):
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)

        with open(self.output_file, "w", encoding=self.encoding, newline="") as f:
            while True:
                data = self.queue.get()
                if data == "DONE":
                    break

                for row in data:
                    line = self.col_delimiter.join(str(col) for col in row)
                    f.write(line + self.row_delimiter)  # ✅ LF/CRLF

# =========================
# File Service
# =========================
class FileService:
    @staticmethod
    def post_process(validate_file, input_file, reject_file, total_errors):
        try:
            if total_errors > 0:
                if os.path.exists(validate_file):
                    shutil.copy(validate_file, input_file)
                    os.remove(validate_file)
                    msg = f"File {validate_file} copied to replace {input_file}\n"
                    msg += f"Reject File: {reject_file}\n"
                    return msg
                else:
                    return f"Error: Validate file '{validate_file}' does not exist\n"
            else:
                os.remove(reject_file)
                os.remove(validate_file)
                return "No errors found. Nothing to copy\n"
        except FileNotFoundError:
            print(f"Error: File not found.")
            exit(1)
        

# =========================
# Report Service
# =========================
class ReportService:
    @staticmethod
    def write(summary_file, data):
        os.makedirs(os.path.dirname(summary_file), exist_ok=True)

        with open(summary_file, "a", encoding="utf-8") as f:
            f.write("=== Validation Summary ===\n")
            for k, v in data.items():
                f.write(f"{k}: {v}\n")


# =========================
# Processor (Main)
# =========================
class Processor:
    def __init__(self, config):
        self.config = config
        self.cpu = mp.cpu_count()

    def run(self):
        for meta in self.config["meta"]:
            self._process_file(meta)

    def _process_file(self, meta):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_file = f"{self.config['input_path']}{meta['file_name']}{self.config['file_extension']}"
        validate_file = f"{self.config['validate_path']}{meta['file_name']}{self.config['file_extension']}"
        reject_file = f"{self.config['reject_path']}{meta['file_name']}-{timestamp}_reject.txt"
        summary_file = f"{self.config['summary_path']}{meta['file_name']}.summary.txt"

        col_delimiter = meta.get("column_delimiter", self.config["column_delimiter"])
        row_delimiter = meta.get("row_delimiter", self.config["row_delimiter"])
        encoding = meta.get("endcoding") or EncodingService.detect(input_file)

        print(f"✔ Start: {input_file}")        

        validator = Validator(meta["columns"], meta.get("header_row", 0))
        reader = ChunkReader(input_file, col_delimiter, self.config.get("chunk_size", 500), encoding)

        clean_q = mp.Queue()
        error_q = mp.Queue()

        clean_writer = mp.Process(target=Writer(clean_q, validate_file, col_delimiter, row_delimiter, encoding).run)
        error_writer = mp.Process(target=Writer(error_q, reject_file, col_delimiter, row_delimiter, encoding).run)

        clean_writer.start()
        error_writer.start()

        total_rows = 0
        total_errors = 0

        with mp.Pool(self.cpu) as pool:
            results = pool.starmap(
                validator.process_chunk,
                ((chunk, row_num) for chunk, row_num in reader)
            )

        for idx, (valid_rows, error_rows, error_count, chunk_len) in enumerate(
                results, start=1
            ):
            clean_q.put(valid_rows)
            error_q.put(error_rows)
            total_rows += chunk_len
            total_errors += error_count

            if idx % 10 == 0:
                print(f"Processed {idx * self.config.get("chunk_size", 500)} lines...")

        clean_q.put("DONE")
        error_q.put("DONE")

        clean_writer.join()
        error_writer.join()

        msg = FileService.post_process(
            validate_file, input_file, reject_file, total_errors
        )

        ReportService.write(summary_file, {
            "Run Date": datetime.now(),
            "Input File": input_file,
            "Total Rows": total_rows,
            "Valid Rows": total_rows - total_errors,
            "Error Rows": total_errors,
            "Message": msg
        })

        print(f"✅ Done: {input_file} | rows={total_rows} errors={total_errors}")


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    conf_root_path = f"{args.conf_root_path}"
    conf_pack_path = f"{args.conf_pack_path}"

    loader = ConfigLoader(
        f"{args.conf_root_path}",
        f"{args.conf_pack_path}"
    )

    config = loader.load()

    processor = Processor(config)
    processor.run()