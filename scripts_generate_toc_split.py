from src.structure.toc_splitter import write_toc_split_outputs

source_path = "logs/run_2026-04-18_06-42-01/09_final_headings.json"
toc_output_path = "logs/run_2026-04-18_06-42-01/toc.json"
final_output_path = "logs/run_2026-04-18_06-42-01/final_headings_only.json"

write_toc_split_outputs(source_path, toc_output_path, final_output_path)
print("done")
