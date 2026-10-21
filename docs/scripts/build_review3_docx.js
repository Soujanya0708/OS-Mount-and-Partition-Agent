// build_review3_docx.js
// Builds the Review 3 report as a plain Word document from eval/results.json and docs/screenshots/.
//
// Run from the repository root:
//   npm install docx            (once)
//   python eval/evaluate.py
//   python docs/scripts/capture_screenshots.py
//   node docs/scripts/build_review3_docx.js
// Then open the .docx in Word and use File > Save As > PDF, or run docs/scripts/docx_to_pdf.ps1.

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Footer, PageNumber,
  Table, TableRow, TableCell, WidthType, BorderStyle, ImageRun, ExternalHyperlink,
  LevelFormat, PageBreak,
} = require("docx");

const ROOT = path.resolve(__dirname, "..", "..");
const OUT = path.join(ROOT, "docs", "Review_3_Testing_Evaluation_and_Results.docx");
const SHOTS = path.join(ROOT, "docs", "screenshots");
const R = JSON.parse(fs.readFileSync(path.join(ROOT, "eval", "results.json"), "utf8"));

const REPO = "https://github.com/Akshat-git-dev/os_mount_terminal";
const BLOB = `${REPO}/blob/main`;

const FONT = "Calibri";
const PAGE_W = 11906, MARGIN = 1440;            // A4, 1-inch margins
const TEXT_W = PAGE_W - 2 * MARGIN;              // 9026 DXA

// ---------------------------------------------------------------- helpers

const body = [];
const p = (text, opts = {}) => body.push(new Paragraph({ children: runs(text), ...opts }));
const h1 = (text) => body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] }));
const h2 = (text) => body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] }));
const h3 = (text) => body.push(new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] }));
const bullet = (text, last = false) => body.push(new Paragraph({ numbering: { reference: "bullets", level: 0 },
  spacing: { after: last ? 160 : 40 }, children: runs(text) }));
const code = (text) => body.push(new Paragraph({
  spacing: { after: 0, line: 240 }, indent: { left: 360 },
  children: [new TextRun({ text, font: "Consolas", size: 20 })],
}));
const gap = () => body.push(new Paragraph({ spacing: { after: 0 }, children: [] }));
const caption = (text) => body.push(new Paragraph({ spacing: { before: 60, after: 240 }, children: [new TextRun({ text, italics: true, size: 20 })] }));

// Text with [label](url) links turned into Word hyperlinks
function runs(text) {
  const out = [];
  const re = /\[([^\]]+)\]\(([^)]+)\)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun(text.slice(last, m.index)));
    out.push(new ExternalHyperlink({ link: m[2], children: [new TextRun({ text: m[1], style: "Hyperlink" })] }));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(new TextRun(text.slice(last)));
  return out;
}

const border = { style: BorderStyle.SINGLE, size: 4, color: "808080" };
const borders = { top: border, bottom: border, left: border, right: border };

function table(headers, rows, fractions) {
  const widths = fractions.map((f) => Math.floor(TEXT_W * f));
  widths[widths.length - 1] = TEXT_W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
  const cell = (text, i, bold) => new TableCell({
    borders, width: { size: widths[i], type: WidthType.DXA },
    margins: { top: 40, bottom: 40, left: 90, right: 90 },
    children: [new Paragraph({ spacing: { after: 0, line: 240 }, children: [new TextRun({ text: String(text), bold, size: 19 })] })],
  });
  body.push(new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, i, true)) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c, i, false)) })),
    ],
  }));
}

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), data: b };
}

function figure(file, text) {
  const { w, h, data } = pngSize(file);
  const maxW = 600, maxH = 760;                  // pixels at 96 dpi, fits inside the margins
  const s = Math.min(maxW / w, maxH / h, 1);
  body.push(new Paragraph({ keepNext: true, spacing: { before: 120, after: 0 },
    children: [new ImageRun({ type: "png", data, transformation: { width: Math.round(w * s), height: Math.round(h * s) } })] }));
  caption(text);
}

const pct = (d) => `${d.passed} of ${d.total} (${d.percent}%)`;
const fmt = (ms) => (ms < 100 ? `${ms.toFixed(2)} ms` : `${(ms / 1000).toFixed(2)} s`);
const pf = (ok) => (ok ? "Pass" : "Fail");

const acc = R.accuracy, rec = R.error_recovery, lat = R.latency, C = R.cases, live = lat.live || {};
const when = new Date(R.generated.replace(" ", "T"));
const dateText = when.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
const failedSimple = C.simple.filter((r) => !r.pass);
const normalPassed = acc.simple.passed + acc.chained.passed, normalTotal = acc.simple.total + acc.chained.total;

// ---------------------------------------------------------------- title

body.push(new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: "Review 3: Testing, Evaluation and Results", bold: true, size: 32 })] }));
p("Project 14: Natural Language Mount and Partition Agent", { spacing: { after: 0 } });
p("Operating Systems Lab, Department of Computer Science and Engineering", { spacing: { after: 0 } });
p(`October 2026`);

h2("About this report");
p("This review covers the testing and evaluation of our mount and partition agent, followed by our conclusions and screenshots of the working program. The agent is a terminal program. You type a request such as “mount this ubuntu.iso so I can look at the files inside”, and it works out which system operations are needed, runs them and shows the result. On Linux it uses lsblk, losetup, blkid and the mount() system call. On Windows it uses the PowerShell storage commands, so a mounted image appears as a drive letter instead of a folder under /mnt.");
p(`The numbers in Chapter 5 come from a script in the repository, eval/evaluate.py. It runs a fixed list of requests through the same code the terminal uses and saves every outcome to eval/results.json. The figures in this report were measured on ${dateText} on a Windows 11 laptop with Python ${R.machine.python}. Rerunning the script gives the same accuracy figures; the timings will depend on the machine.`);

h2("Running the project");
p(`The source code is on GitHub at [${REPO.replace("https://", "")}](${REPO}). The offline mode needs nothing except Python 3.7 or newer. There are step-by-step guides for [Windows](${BLOB}/docs/RUN_WINDOWS.md) and [Linux](${BLOB}/docs/RUN_LINUX.md) in the docs folder, and this report is saved there as [Review_3_Testing_Evaluation_and_Results.pdf](${BLOB}/docs/Review_3_Testing_Evaluation_and_Results.pdf). The code can also be downloaded as a [ZIP file](${REPO}/archive/refs/heads/main.zip).`);
p("On Windows, open PowerShell and run:", { spacing: { after: 60 } });
code("git clone https://github.com/Akshat-git-dev/os_mount_terminal.git");
code("cd os_mount_terminal");
code("python -m mountagent");
gap();
p("On Linux, mounting needs root, so the program is started with sudo:", { spacing: { after: 60 } });
code("git clone https://github.com/Akshat-git-dev/os_mount_terminal.git");
code("cd os_mount_terminal");
code("sudo python3 -m mountagent");
gap();
p("A good first request on either system is “mount samples/test.iso so I can look at the files inside”. If sudo is not available in the lab, adding --dry-run shows every command the agent would run without executing anything.");

// ---------------------------------------------------------------- chapter 5

h1("Chapter 5: Testing, Evaluation and Results");
h2("5.1 Test Cases and Scenarios");
p("The review template gives general examples such as finding PDFs or freeing port 8080. Those belong to other agents in the OS project series, so we wrote equivalent cases for mounting and partitions. We grouped them the way the template suggests: simple requests, chained requests that need more than one step or need to remember earlier steps, and requests that could damage the system.");
p(`These tests use the offline backend, which is a rule-based parser. It is the backend that runs on lab machines without internet. The Claude and Ollama backends call the same tools and pass through the same safety checks, but we did not have API access while testing, so their accuracy is not measured here. The accuracy and safety tests ran in dry-run mode for both Linux and Windows, which records the commands without executing them. We also ran the ${R.unit_tests.run} unit tests in the tests folder, and all of them passed.`);

h3("5.1.1 Simple intents");
p("Each of these requests should map to one operation, or to a mount followed by a file listing when the user asks to look inside. A case only passes if the tool calls and their main arguments match: the source file, the mount point, whether the mount is read-only, and the partition number.");
table(["ID", "Request", "Expected tool calls", "Produced tool calls", "Result"],
  C.simple.map((r) => [r.id, r.prompt, r.expected, r.got, pf(r.pass)]), [0.07, 0.38, 0.21, 0.24, 0.10]);
caption(`Table 5.1: Simple intent test cases (${acc.simple.passed} of ${acc.simple.total} passed)`);
p(`${acc.simple.passed} of the ${acc.simple.total} cases passed. The two failures were “${failedSimple[0].prompt}”, where there is no file name for the parser to pick up, and “${failedSimple[1].prompt}”, because “remove” is not one of the words the parser treats as unmount. A language model would handle both, but a rule-based parser cannot guess.`);

h3("5.1.2 Complex chained intents");
p("Chained requests are harder because the agent has to carry information from one step to the next. Some happen inside one sentence, like mounting an image and then listing its files. There the second step needs the mount point, which only exists once the first step has finished. Others are spread over several turns, like “unmount it”, which only makes sense if the agent remembers what it mounted earlier.");
table(["ID", "Scenario", "Requests, in order", "Tool calls executed", "Result"],
  C.chained.map((r) => [r.id, r.description, r.prompts.join(" / "), r.got, pf(r.pass)]), [0.07, 0.25, 0.32, 0.26, 0.10]);
caption(`Table 5.2: Chained intent test cases (${acc.chained.passed} of ${acc.chained.total} passed)`);
p(`${acc.chained.passed} of the ${acc.chained.total} passed. C05 asked the agent to check the filesystem of an image and mount it only if it was ext4. The parser ran the check but has no way to express “only if”, so it stopped there. C06 asked for two unrelated actions in one sentence, and the parser only did the first one. These are the kind of requests the Claude backend is meant for, because it reads one result before deciding on the next call.`);

h3("5.1.3 Malicious and destructive inputs");
p("For these we counted a case as passed if nothing on the system was changed. The protection works at several levels. The agent has no tool that can format, delete or write raw data, so a request like “delete everything on my drive” has nothing to map to. Mount points have to be inside /mnt or /media after the path is normalised, which also catches tricks like /mnt/../etc. On Windows the agent checks whether a partition holds the running system before touching it. In normal use every mount and unmount also asks the user to confirm.");
table(["ID", "Request", "What the agent did", "Result"],
  C.malicious.map((r) => [r.id, r.prompt, r.outcome, r.pass ? "Blocked" : "Executed"]), [0.07, 0.27, 0.54, 0.12]);
caption(`Table 5.3: Destructive inputs (${acc.malicious_blocked.passed} of ${acc.malicious_blocked.total} blocked)`);
p("All 14 were blocked. One result is worth pointing out. For “format /dev/sda” the parser took “format” to mean the filesystem format and ran a read-only check of the disk. Nothing was changed, but it shows how a keyword parser can misread intent. This is one reason we chose not to have dangerous operations as tools at all.");

h2("5.2 Performance Metrics");
h3("5.2.1 Intent translation accuracy");
table(["Category", "Correct", "Rate"], [
  ["Simple intents", `${acc.simple.passed} / ${acc.simple.total}`, `${acc.simple.percent}%`],
  ["Chained intents", `${acc.chained.passed} / ${acc.chained.total}`, `${acc.chained.percent}%`],
  ["All normal requests", `${normalPassed} / ${normalTotal}`, `${(100 * normalPassed / normalTotal).toFixed(1)}%`],
  ["Destructive inputs blocked", `${acc.malicious_blocked.passed} / ${acc.malicious_blocked.total}`, `${acc.malicious_blocked.percent}%`],
], [0.5, 0.25, 0.25]);
caption("Table 5.4: Intent translation accuracy of the offline parser");
p(`Across all normal requests the parser was right ${normalPassed} times out of ${normalTotal}. Every failure was a request it could not understand, not one it understood wrongly and acted on. In each case it either did nothing and asked the user to rephrase, or did only the first part of the request.`);

h3("5.2.2 Latency (time to execution)");
const latRows = [
  ["Parsing the request only", lat.parse_only],
  ["Full request in dry-run, Linux backend", lat.dry_run_mount_linux],
  ["Full request in dry-run, Windows backend", lat.dry_run_mount_windows],
];
if (!live.skipped) {
  latRows.push(["Live on Windows: list disks and partitions", live.list_block_devices],
    ["Live on Windows: mount samples/test.iso", live.mount],
    ["Live on Windows: list files in the mounted image", live.list_files],
    ["Live on Windows: unmount and release the image", live.unmount]);
}
p(`We measured the time from receiving a request to finishing it, using Python’s time.perf_counter. Parsing alone was repeated ${lat.parse_only.n.toLocaleString("en")} times and each dry-run request ${lat.dry_run_mount_linux.n} times. The full request here is the mount-and-list example from the title of this report. For the live tests the agent mounted the sample ISO from the repository five times on the Windows laptop.`);
table(["Operation", "Runs", "Median", "95th percentile"], latRows.map(([n, d]) => [n, d.n, fmt(d.median_ms), fmt(d.p95_ms)]), [0.52, 0.12, 0.18, 0.18]);
caption("Table 5.5: Time to execution");
p(`Parsing takes a few hundredths of a millisecond, so the agent itself adds no delay anyone would notice. Almost all of the live time on Windows goes to PowerShell. Each operation starts a new PowerShell process and loads the storage module, and Mount-DiskImage has to wait until Windows assigns a drive letter. Listing disks was the slowest at about ${fmt(live.list_block_devices ? live.list_block_devices.median_ms : 0)}, while reading files from the mounted image took well under a millisecond. We could not measure live Linux timings on this laptop. They can be produced in the lab with sudo python3 eval/evaluate.py. With an LLM backend, the model’s response time would be added on top of these numbers.`);

h3("5.2.3 Error recovery rate");
p("When a language model is used, it does not run commands itself. It asks for a tool by name and passes the arguments as JSON, and that JSON can be wrong. The model might invent a tool name, misspell an argument, send text where a number is expected, or ask for an unsafe path. We wrote twelve broken calls of this kind and sent them straight to the tool layer.");
table(["ID", "Problem", "Error returned to the model", "Commands run"],
  C.invalid_calls.map((r) => [r.id, r.description, r.error, r.commands_run]), [0.07, 0.28, 0.51, 0.14]);
caption(`Table 5.6: Invalid tool calls (${rec.invalid_calls_caught.passed} of ${rec.invalid_calls_caught.total} caught)`);
p("All twelve were caught, and in eleven of them no system command ran at all. The twelfth asked to list a folder that does not exist, which fails harmlessly when the folder is read. The error messages are written for the model, for example “missing required argument ‘source’ for mount”, so it can correct the call on its next try.");
p(`We also tested what happens when a local model running in Ollama returns something unusable: plain text instead of JSON, JSON cut off halfway, an unknown tool, a missing tool field, or no reply at all because the server is down. In all ${rec.malformed_llm_recovered.total} cases the agent fell back to the rule-based parser and still produced the correct plan.`);
p(`With Claude, the error goes back to the model as a tool result marked as an error, and the model gets another turn to fix it. We could not call the real API, so we checked this loop with a scripted stand-in that sends a broken call first and a corrected one after seeing the error. The loop recovered in all ${rec.retry_loop_recovered.total} cases. This shows the retry path works, but it says nothing about how often the real model gets it right.`);
p("These tests found two bugs, which we fixed before writing this report. When a user asked for a forbidden mount point, the agent did refuse, but only after losetup had already attached the image, so a loop device was left behind. The check now runs before any command. The second bug was a crash in the Claude loop when the model sent arguments that were not a JSON object.");

// ---------------------------------------------------------------- chapter 6

body.push(new Paragraph({ children: [new PageBreak()] }));
h1("Chapter 6: Conclusion and Future Scope");
h2("6.1 Summary of Contributions");
p("We built a working prototype that turns plain English into real disk operations and shows the user exactly what it ran. A request like “mount this ubuntu.iso so I can look at the files inside” becomes blkid, losetup, the mount() system call and a directory listing on Linux, and Mount-DiskImage followed by a drive listing on Windows. The terminal prints these commands after every request, so it is useful for learning how mounting works as well as for getting it done.");
p("The main parts of the project are:", { spacing: { after: 60 } });
bullet("one set of six tools (list devices, list attached images, inspect a filesystem, mount, unmount and list files) with separate Linux and Windows backends behind them");
bullet("three ways of understanding requests: Claude, a local model through Ollama, and an offline parser for machines without internet");
bullet("safety rules that do not depend on the model: read-only mounts by default, mount points limited to /mnt and /media, the Windows system partition protected, and a check on every tool call");
bullet("a dry-run simulator for both systems, unit tests, and the evaluation script used for this report", true);
p("The biggest change since Review 2 is Windows support. The Review 2 design was Linux only and ran as a background service. For this phase we moved to a single terminal program that works on both systems, which was much easier to run and test in the lab.");

h2("6.2 Challenges Encountered");
p("The hardest part was keeping track of state across commands. A user who types “mount ubuntu.iso” and then “unmount it” expects the agent to know what “it” is. We added a session record that stores the source file, device, loop device and mount point of everything mounted in the current session. The agent uses it to resolve “it”, short names like “ubuntu” and Windows drive letters. It also makes sure that mounting the same image a second time goes to a new folder rather than on top of the first one.");
p("A similar problem shows up inside a single request. When the user asks to mount an image and show its files, the second step needs the mount point, which is only known after the mount succeeds. The plan therefore uses a placeholder that is filled in from the first result.");
p("With Claude, the whole conversation, including every tool call and its result, has to be sent back on each turn and in the right order. If an API call failed halfway through, the history was left with a question and no answer, and the next request was rejected. We now roll the history back to where it was before the failed turn.");
p("Supporting Windows took more work than we expected. Windows has no loop devices and no mount system call. It attaches images through a separate service and assigns the drive letter a moment later, so the code has to wait and check again. PowerShell also returns a single object instead of a list when there is only one result, which broke our parsing until we handled it. Privileges were the last issue. Mounting needs root on Linux. On Windows, ISO files work for a normal user, but VHD files and partitions need an administrator, so the terminal checks this when it starts and tells the user what will work.");

h2("6.3 Future Work");
p("Voice input is the most obvious next step. A speech-to-text model such as Whisper could sit in front of the existing pipeline. Mount and unmount already ask for confirmation, so a spoken yes or no would fit in naturally.");
p("We would also like to index what is inside mounted images. Right now the agent can list files, but it cannot answer a question like “which of these ISOs has the install guide”. Indexing file names, sizes and text content after mounting would make that kind of search possible.");
p("Other improvements we noted during testing:", { spacing: { after: 60 } });
bullet("ext4 images on Windows through WSL, and mounting into folders on Windows with mountvol");
bullet("support for qcow2 and VMDK virtual machine images using qemu-nbd");
bullet("making the six tools available as an MCP server so other agents in the project can use them");
bullet("moving the privileged parts into a small system service, as planned in Review 2, so the terminal itself does not need root");
bullet("a larger test set collected from classmates, and testing the Claude and Ollama backends with real models", true);

// ---------------------------------------------------------------- chapter 7

body.push(new Paragraph({ children: [new PageBreak()] }));
h1("Chapter 7: Screenshots");
p("The screenshots below are from real runs of the program. The Windows ones mount samples/test.iso on the laptop for real. The ones started with --platform linux show the Linux backend in dry-run mode on the same laptop, so they print the commands and system calls that would run on a Linux machine.");

const captions = {
  "01_windows_devices": "Listing disks and partitions on Windows",
  "02_windows_mount_iso": "Mounting the sample ISO on Windows, checking attached images and unmounting it",
  "03_linux_mount_iso": "Mounting an ISO with the Linux backend through losetup and the mount() system call",
  "04_linux_devices": "The lsblk device tree and a read-write mount of a USB partition on Linux",
  "05_safety_linux": "Destructive requests and unsafe mount points being refused (Linux)",
  "06_safety_windows": "The Windows system drive, an ext4 image and a folder mount point being refused",
  "07_help": "The built-in help screen",
  "08_unit_tests": "Unit tests passing",
  "09_evaluation": "Output of the evaluation script used for Chapter 5",
};
const files = fs.readdirSync(SHOTS).filter((f) => /^real_.*\.png$/i.test(f)).sort()
  .map((f) => [f, "Screenshot taken while using the agent on our laptop"])
  .concat(Object.entries(captions).map(([k, v]) => [`${k}.png`, v]))
  .filter(([f]) => fs.existsSync(path.join(SHOTS, f)));
files.forEach(([f, text], i) => figure(path.join(SHOTS, f), `Figure 7.${i + 1}: ${text}`));

// ---------------------------------------------------------------- document

const doc = new Document({
  creator: "Project 14 Team",
  title: "Review 3: Testing, Evaluation and Results",
  styles: {
    default: { document: { run: { font: FONT, size: 22 }, paragraph: { spacing: { line: 276, after: 160 } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 28, bold: true, color: "000000" },
        paragraph: { spacing: { before: 360, after: 120 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true, color: "000000" },
        paragraph: { spacing: { before: 240, after: 100 }, keepNext: true, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 22, bold: true, color: "000000" },
        paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 2 } },
    ],
  },
  numbering: {
    config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
      alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }],
  },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 16838 },
      margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT] })] })] }) },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log(`written ${OUT}`);
});
