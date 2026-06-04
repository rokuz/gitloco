import { refractor } from "refractor";
import tsx from "refractor/tsx";
import jsx from "refractor/jsx";
refractor.register(tsx); refractor.register(jsx);

const samples = {
  c: `#include <stdio.h>\nint main() {\n  // hi\n  printf("hello %s\\n", "world");\n  return 0;\n}`,
  cpp: `#include <iostream>\nstd::string greet(const std::string& name) {\n  return "hello " + name;\n}\n// note`,
  python: `from typing import Iterable\ndef greet(name: str) -> None:\n    """Say hi."""\n    print(f"Hello, {name}!")`,
};
function classes(node, acc = new Set()) {
  if (!node) return acc;
  if (node.properties?.className) for (const c of node.properties.className) acc.add(c);
  if (node.children) for (const ch of node.children) classes(ch, acc);
  return acc;
}
for (const [lang, code] of Object.entries(samples)) {
  const root = refractor.highlight(code, lang);
  console.log(`\n=== ${lang} ===`);
  console.log("classes:", Array.from(classes(root)).sort().join(", "));
}
