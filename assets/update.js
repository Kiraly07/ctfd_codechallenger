/* Admin update page.
 *
 * The core challenge page serializes the update form with serializeJSON and
 * PATCHes /api/v1/challenges/<id>. That serializer collapses same-name
 * checkboxes to one boolean, and CTFd.fetch captured window.fetch at boot,
 * so this file reads the Judge0 fields itself on submit and merges them
 * into that one PATCH.
 *
 * Test cases are saved immediately through the plugin admin API, not through
 * the challenge PATCH, so adding a case does not depend on clicking Update.
 *
 * The script tag is `defer`, but bind on DOMContentLoaded anyway: a cached
 * page can run this before #judge0-tests exists.
 */
(function () {
  function boot() {
    var box = document.getElementById("judge0-tests");
    if (!box) {
      return;
    }
    bind(box);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  function bind(box) {
  var root = (window.CTFd && CTFd.config && CTFd.config.urlRoot) || "";
  var challengeId = box.getAttribute("data-challenge-id");

  function api(path, options) {
    options = options || {};
    options.method = options.method || "GET";
    options.headers = options.headers || {};
    options.headers.Accept = "application/json";
    if (options.body && typeof options.body !== "string") {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }
    return CTFd.fetch(path, options).then(function (response) {
      return response.json().then(function (body) {
        if (!response.ok || body.success === false) {
          var message = (body && (body.message || (body.errors && JSON.stringify(body.errors)))) || "Request failed";
          throw new Error(message);
        }
        return body;
      });
    });
  }

  function field(label, name, value, multiline) {
    var wrap = document.createElement("div");
    wrap.className = "form-group";
    var lab = document.createElement("label");
    lab.textContent = label;
    wrap.appendChild(lab);
    var input;
    if (multiline) {
      input = document.createElement("textarea");
      input.rows = 3;
    } else {
      input = document.createElement("input");
      input.type = "text";
    }
    input.className = "form-control";
    input.name = name;
    input.value = value || "";
    wrap.appendChild(input);
    return { wrap: wrap, input: input };
  }

  function render(cases) {
    box.innerHTML = "";
    if (!cases.length) {
      box.innerHTML = '<p class="text-muted">No test cases yet.</p>';
    }
    cases.forEach(function (item, index) {
      var card = document.createElement("div");
      card.className = "card mb-2";
      var body = document.createElement("div");
      body.className = "card-body";

      var title = document.createElement("strong");
      title.textContent = "Test " + (index + 1);
      body.appendChild(title);

      var name = field("Name (optional)", "name", item.name, false);
      var stdin = field("Input", "stdin", item.stdin, true);
      var expected = field("Expected output", "expected_output", item.expected_output, true);
      body.appendChild(name.wrap);
      body.appendChild(stdin.wrap);
      body.appendChild(expected.wrap);

      var sampleWrap = document.createElement("div");
      sampleWrap.className = "form-check mb-2";
      var sample = document.createElement("input");
      sample.type = "checkbox";
      sample.className = "form-check-input";
      sample.checked = !!item.is_sample;
      var sampleLabel = document.createElement("label");
      sampleLabel.className = "form-check-label";
      sampleLabel.textContent = "Sample (visible to players)";
      sampleWrap.appendChild(sample);
      sampleWrap.appendChild(sampleLabel);
      body.appendChild(sampleWrap);

      var save = document.createElement("button");
      save.type = "button";
      save.className = "btn btn-sm btn-success mr-2";
      save.textContent = "Save";
      var del = document.createElement("button");
      del.type = "button";
      del.className = "btn btn-sm btn-outline-danger";
      del.textContent = "Delete";
      body.appendChild(save);
      body.appendChild(del);
      card.appendChild(body);
      box.appendChild(card);

      save.addEventListener("click", function () {
        save.disabled = true;
        api("/plugins/judge0/admin/tests/" + item.id, {
          method: "PATCH",
          body: {
            name: name.input.value,
            stdin: stdin.input.value,
            expected_output: expected.input.value,
            is_sample: sample.checked,
          },
        })
          .then(load)
          .catch(function (err) {
            window.alert(err.message);
            save.disabled = false;
          });
      });

      del.addEventListener("click", function () {
        if (!window.confirm("Delete this test case?")) {
          return;
        }
        api("/plugins/judge0/admin/tests/" + item.id, { method: "DELETE" })
          .then(load)
          .catch(function (err) {
            window.alert(err.message);
          });
      });
    });
  }

  function load() {
    return api("/plugins/judge0/admin/" + challengeId + "/tests").then(function (body) {
      render(body.data || []);
    });
  }

  document.getElementById("judge0-add-test").addEventListener("click", function () {
    api("/plugins/judge0/admin/" + challengeId + "/tests", {
      method: "POST",
      body: { name: "", stdin: "", expected_output: "", is_sample: false },
    })
      .then(load)
      .catch(function (err) {
        window.alert(err.message);
      });
  });

  // CTFd.fetch captured window.fetch at boot, so wrapping window.fetch later
  // does nothing. serializeJSON also collapses same-name checkboxes to a
  // single true/false. Read the Judge0 fields ourselves and hand the core
  // form only the columns it already understands.
  var form = document.querySelector("#challenge-update-container > form");
  if (form) {
    form.addEventListener(
      "submit",
      function () {
        var payload = {};
        payload.judge0_url = (form.querySelector("[name=judge0_url]") || {}).value || "";
        payload.cpu_time_limit = (form.querySelector("[name=cpu_time_limit]") || {}).value;
        payload.memory_limit = (form.querySelector("[name=memory_limit]") || {}).value;
        payload.comparison_mode = (form.querySelector("[name=comparison_mode]") || {}).value || "trim";
        payload.allowed_languages = Array.prototype.map.call(
          form.querySelectorAll("[name=allowed_languages]:checked"),
          function (box) {
            return box.value;
          }
        );
        var starter = {};
        form.querySelectorAll("textarea[name^='starter_code_']").forEach(function (area) {
          var slug = area.name.slice("starter_code_".length);
          if (area.value) {
            starter[slug] = area.value;
          }
          area.disabled = true;
        });
        payload.starter_code = starter;
        form.querySelectorAll("[name=allowed_languages]").forEach(function (box) {
          box.disabled = true;
        });
        ["judge0_url", "cpu_time_limit", "memory_limit", "comparison_mode"].forEach(function (name) {
          var el = form.querySelector("[name='" + name + "']");
          if (el) {
            el.disabled = true;
          }
        });
        form.setAttribute("data-judge0-payload", JSON.stringify(payload));
      },
      true
    );
  }

  var originalFetch = CTFd.fetch;
  CTFd.fetch = function (url, options) {
    try {
      var target = String(url);
      var extra = form && form.getAttribute("data-judge0-payload");
      if (
        extra &&
        options &&
        options.method === "PATCH" &&
        target.indexOf("/api/v1/challenges/" + challengeId) !== -1 &&
        options.body
      ) {
        var payload = JSON.parse(options.body);
        Object.assign(payload, JSON.parse(extra));
        options = Object.assign({}, options, { body: JSON.stringify(payload) });
        form.removeAttribute("data-judge0-payload");
        form.querySelectorAll(":disabled").forEach(function (el) {
          if (el.name && (el.name.indexOf("starter_code_") === 0 || el.name === "allowed_languages" || el.name === "judge0_url" || el.name === "cpu_time_limit" || el.name === "memory_limit" || el.name === "comparison_mode")) {
            el.disabled = false;
          }
        });
      }
    } catch (err) {
      // Leave the original body untouched if it is not the challenge update.
    }
    return originalFetch.call(CTFd, url, options);
  };

  load().catch(function (err) {
    box.innerHTML = '<p class="text-danger">' + err.message + "</p>";
  });
  }
})();
