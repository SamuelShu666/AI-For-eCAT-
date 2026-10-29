// Ni-RC v2 candidate-pool import. The Python loader reads the masked-result
// sheet only: candidate ID, composition and the 17 element-fraction columns.
// It does not read Δη_RC, global rank or Top 10% during candidate seeding.
// Run from repository root after setting NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD:
//   python members/member-c/build_memory_graph.py --seed-candidates
// It also imports the project manifest's explicitly recorded test conditions.
// The trusted result callback writes only completed experiment returns; it
// never renames cell_voltage_V into Δη_RC or imports held-out workbook labels.
