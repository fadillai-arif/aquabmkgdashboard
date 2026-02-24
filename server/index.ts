import { spawn } from "child_process";

// We spawn the python Flask application which will bind to port 5000
const pythonProcess = spawn("python3", ["app.py"], { 
  stdio: "inherit",
  env: { ...process.env, PORT: "5000" }
});

pythonProcess.on("error", (err) => {
  console.error("Failed to start python process:", err);
});

pythonProcess.on("exit", (code) => {
  process.exit(code || 0);
});