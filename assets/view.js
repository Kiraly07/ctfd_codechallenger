/* Player UI for a Judge0 challenge.
 *
 * CTFd 3.8 loads this file with $.getScript before the modal HTML is inserted,
 * then calls preRender / postRender. postRender is where the editor is built,
 * because that is the first moment #judge0-code exists.
 *
 * CodeMirror is loaded from /plugins/ctfd_code/assets (bundled, no CDN). If it
 * fails, the textarea stays and is used as-is.
 */
(function () {
  var root = (window.CTFd && CTFd.config && CTFd.config.urlRoot) || "";

  CTFd._internal.challenge.data = undefined;
  CTFd._internal.challenge.renderer = null;
  CTFd._internal.challenge.preRender = function () {};
  CTFd._internal.challenge.render = null;
  CTFd._internal.challenge.postRender = function () {
    var node = document.getElementById("judge0-root");
    if (!node || node.getAttribute("data-bound") === "1") {
      return;
    }
    node.setAttribute("data-bound", "1");
    bind(node);
  };

  // The core theme still calls challenge.submit() if a plugin defines it and
  // the player hits the (removed) flag button. Keep a no-op so that path
  // cannot throw. Real grading goes through #judge0-submit.
  CTFd._internal.challenge.submit = function () {
    return Promise.resolve({
      status: 200,
      data: { status: "incorrect", message: "Use the Submit button under the editor." },
    });
  };

  function bind(node) {
    var challengeId = node.getAttribute("data-challenge-id");
    var languageSelect = document.getElementById("judge0-language");
    var textarea = document.getElementById("judge0-code");
    var runButton = document.getElementById("judge0-run");
    var submitButton = document.getElementById("judge0-submit");
    var consoleEl = document.getElementById("judge0-console");
    var statusEl = document.getElementById("judge0-status");
    var samplesEl = document.getElementById("judge0-samples");
    var samplesBody = document.getElementById("judge0-samples-body");

    var editor = null;
    var config = null;
    var busy = false;

    function source() {
      if (editor) {
        return editor.getValue();
      }
      return textarea.value;
    }

    function setSource(value) {
      if (editor) {
        editor.setValue(value || "");
      } else {
        textarea.value = value || "";
      }
    }

    function setBusy(on) {
      busy = on;
      runButton.disabled = on;
      submitButton.disabled = on;
    }

    function badge(status) {
      var kind = "internal";
      if (status === "Accepted") kind = "accepted";
      else if (status === "Wrong Answer") kind = "wrong";
      else if (status === "Compilation Error") kind = "compile";
      else if (status === "Time Limit Exceeded" || status === "Memory Limit Exceeded") kind = "limit";
      else if (status && status.indexOf("Runtime") === 0) kind = "runtime";
      else if (status === "Internal Error") kind = "internal";
      var mark = {
        accepted: "Accepted",
        wrong: "Wrong Answer",
        runtime: status,
        limit: status,
        compile: "Compilation Error",
        internal: status || "Error",
      }[kind];
      return '<span class="judge0-badge judge0-badge-' + kind + '">' + escapeHtml(mark) + "</span>";
    }

    function escapeHtml(value) {
      return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    }

    function renderSamples(samples) {
      if (!samples || !samples.length) {
        samplesEl.hidden = true;
        return;
      }
      samplesEl.hidden = false;
      samplesBody.innerHTML = samples
        .map(function (sample, index) {
          var title = sample.name || "Sample " + (index + 1);
          return (
            '<div class="judge0-sample"><div><strong>' +
            escapeHtml(title) +
            "</strong></div>" +
            "<div>Input</div><pre>" +
            escapeHtml(sample.stdin) +
            "</pre>" +
            "<div>Expected</div><pre>" +
            escapeHtml(sample.expected_output) +
            "</pre></div>"
          );
        })
        .join("");
    }

    function renderResult(body, isSubmit) {
      var lines = [];
      lines.push(badge(body.status) + " " + escapeHtml(body.message || ""));
      if (typeof body.passed === "number") {
        lines.push(escapeHtml(body.passed + " / " + body.total + " tests passed"));
      }
      (body.cases || []).forEach(function (item) {
        var block = '<div class="judge0-case"><div class="judge0-case-title">' + badge(item.status) + escapeHtml(item.name || "") + "</div>";
        if (item.sample !== false && (item.stdout || item.stderr || item.compile_output || item.stdin)) {
          if (item.compile_output) {
            block += "compile\n" + escapeHtml(item.compile_output) + "\n";
          }
          if (item.stderr) {
            block += "stderr\n" + escapeHtml(item.stderr) + "\n";
          }
          if (item.stdout) {
            block += "stdout\n" + escapeHtml(item.stdout);
          }
          if (item.time) {
            block += "\ntime " + escapeHtml(item.time) + "s";
          }
          if (item.memory) {
            block += "  memory " + escapeHtml(item.memory) + " KB";
          }
        }
        block += "</div>";
        lines.push(block);
      });
      consoleEl.innerHTML = lines.join("\n");
      statusEl.innerHTML = badge(body.status);

      if (isSubmit && (body.status === "Accepted" || body.solved)) {
        // Tell the Alpine challenge component the submission was correct so
        // the solved state, next-challenge button and rating block appear.
        try {
          var alpineRoot = document.querySelector("[x-data='Challenge'], [x-data=\"Challenge\"]");
          if (alpineRoot && window.Alpine) {
            var data = window.Alpine.$data(alpineRoot);
            data.response = {
              data: { status: "correct", message: body.message || "Accepted" },
            };
            if (typeof data.renderSubmissionResponse === "function") {
              data.renderSubmissionResponse();
            }
          }
        } catch (err) {
          // The solve is already stored. A missing Alpine hook only skips the banner.
        }
      }
    }

    function post(path) {
      if (busy) {
        return;
      }
      var code = source();
      if (!code.trim()) {
        consoleEl.textContent = "Write some code first.";
        return;
      }
      var language = languageSelect.value;
      setBusy(true);
      consoleEl.textContent = "Running...";
      CTFd.fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ source_code: code, language: language }),
      })
        .then(function (response) {
          return response.json().then(function (body) {
            return { http: response.status, body: body };
          });
        })
        .then(function (result) {
          var body = result.body || {};
          if (!body.status && body.message) {
            body.status = "Internal Error";
          }
          renderResult(body, path.indexOf("/submit/") !== -1);
        })
        .catch(function () {
          consoleEl.textContent = "The request failed before Judge0 returned a result.";
        })
        .then(function () {
          setBusy(false);
          if (editor) {
            editor.focus();
          }
        });
    }

    function applyLanguage() {
      if (!config) {
        return;
      }
      var slug = languageSelect.value;
      var starter = (config.starter_code && config.starter_code[slug]) || "";
      if (!source().trim() || source() === textarea.getAttribute("data-last-starter")) {
        setSource(starter);
        textarea.setAttribute("data-last-starter", starter);
      }
      if (editor) {
        var mode = "text/plain";
        (config.languages || []).forEach(function (item) {
          if (item.slug === slug) {
            mode = item.mode;
          }
        });
        editor.setOption("mode", mode);
      }
    }

    function loadEditor() {
      var base = root + "/plugins/ctfd_code/assets/vendor/codemirror/";
      return loadScript(base + "codemirror.min.js")
        .then(function () {
          return Promise.all([
            loadScript(base + "mode/python.min.js"),
            loadScript(base + "mode/clike.min.js"),
            loadScript(base + "mode/javascript.min.js"),
            loadScript(base + "mode/go.min.js"),
            loadScript(base + "mode/rust.min.js"),
          ]);
        })
        .then(function () {
          if (!window.CodeMirror) {
            return;
          }
          editor = window.CodeMirror.fromTextArea(textarea, {
            lineNumbers: true,
            indentUnit: 4,
            tabSize: 4,
            indentWithTabs: false,
            lineWrapping: true,
            extraKeys: {
              "Ctrl-Enter": function () {
                runButton.click();
              },
              "Cmd-Enter": function () {
                runButton.click();
              },
            },
          });
        })
        .catch(function () {
          editor = null;
        });
    }

    CTFd.fetch("/plugins/ctfd_code/" + challengeId + "/config", { method: "GET" })
      .then(function (response) {
        return response.json();
      })
      .then(function (payload) {
        config = (payload && payload.data) || { languages: [], samples: [], starter_code: {} };
        languageSelect.innerHTML = "";
        (config.languages || []).forEach(function (item) {
          var option = document.createElement("option");
          option.value = item.slug;
          option.textContent = item.label;
          languageSelect.appendChild(option);
        });
        if (!languageSelect.options.length) {
          consoleEl.textContent = "No languages are enabled for this challenge.";
          setBusy(true);
          return;
        }
        renderSamples(config.samples || []);
        return loadEditor().then(applyLanguage);
      })
      .catch(function () {
        consoleEl.textContent = "Could not load the challenge configuration.";
      });

    languageSelect.addEventListener("change", applyLanguage);
    runButton.addEventListener("click", function () {
      post("/plugins/ctfd_code/run/" + challengeId);
    });
    submitButton.addEventListener("click", function () {
      post("/plugins/ctfd_code/submit/" + challengeId);
    });
    textarea.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        runButton.click();
      }
    });
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[src="' + src + '"]');
      if (existing) {
        if (existing.getAttribute("data-loaded") === "1" || window.CodeMirror) {
          resolve();
          return;
        }
        existing.addEventListener("load", function () {
          resolve();
        });
        existing.addEventListener("error", reject);
        return;
      }
      var script = document.createElement("script");
      script.src = src;
      script.async = false;
      script.onload = function () {
        script.setAttribute("data-loaded", "1");
        resolve();
      };
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }
})();
