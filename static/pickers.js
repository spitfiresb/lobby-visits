// Our own dropdown and date picker for the filter form. Each one hides the
// real <select> or <input>, which still holds the value, so the form submits
// the same query string as before (?from=…&to=…&type=…).

const CHEVRON = '<svg viewBox="0 0 12 12"><path d="M3 4.5l3 3 3-3"/></svg>';

// Wraps a hidden form control in a button that opens a popover below it.
function makePicker(control) {
  const picker = document.createElement("div");
  picker.className = "picker";
  picker.innerHTML = `<button type="button" class="picker-button"><span></span>${CHEVRON}</button>
                      <div class="popover"></div>`;
  control.after(picker);
  control.hidden = true;  // hidden, but still sent when the form is submitted

  picker.querySelector(".picker-button").onclick = () => {
    closePickers(picker);
    picker.classList.toggle("open");
  };
  return picker;
}

function closePickers(except) {
  for (const picker of document.querySelectorAll(".picker.open")) {
    if (picker !== except) picker.classList.remove("open");
  }
}

// Clicking anywhere else, or pressing Escape, closes an open picker.
document.addEventListener("click", (event) => closePickers(event.target.closest(".picker")));
document.addEventListener("keydown", (event) => event.key === "Escape" && closePickers());

function makeDropdown(select) {
  const picker = makePicker(select);
  const label = picker.querySelector(".picker-button span");
  const menu = picker.querySelector(".popover");

  function draw() {
    label.textContent = select.selectedOptions[0]?.text ?? "";  // nothing, for an unknown type in the URL
    menu.innerHTML = [...select.options].map((option) =>
      `<button type="button" class="option${option.selected ? " selected" : ""}"
               data-value="${option.value}">${option.text}</button>`).join("");
  }

  menu.onclick = (event) => {
    const option = event.target.closest(".option");
    if (!option) return;
    select.value = option.dataset.value;
    select.dispatchEvent(new Event("change"));  // so the page can react, as with a real <select>
    picker.classList.remove("open");
    draw();
  };
  draw();
}

function makeDatePicker(input) {
  const picker = makePicker(input);
  const label = picker.querySelector(".picker-button span");
  const popover = picker.querySelector(".popover");
  popover.innerHTML = `
    <div class="month">
      <button type="button" data-step="-1">‹</button><b></b><button type="button" data-step="1">›</button>
    </div>
    <div class="days"></div>
    <button type="button" class="clear">Clear</button>`;

  // The month on screen: the chosen date's month, or this month.
  const shown = input.value ? new Date(input.value + "T00:00") : new Date();
  shown.setDate(1);

  function draw() {
    label.textContent = input.value ? formatDate(input.value) : "Any date";
    label.classList.toggle("muted", !input.value);
    popover.querySelector("b").textContent =
      shown.toLocaleDateString("en-GB", { month: "long", year: "numeric" });

    const year = shown.getFullYear(), month = shown.getMonth();
    const blanks = (new Date(year, month, 1).getDay() + 6) % 7;  // weeks start on Monday
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    let html = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map((d) => `<span>${d}</span>`).join("") +
               "<span></span>".repeat(blanks);
    for (let day = 1; day <= daysInMonth; day++) {
      const date = `${year}-${pad(month + 1)}-${pad(day)}`;
      html += `<button type="button" data-date="${date}"${date === input.value ? ' class="selected"' : ""}>${day}</button>`;
    }
    popover.querySelector(".days").innerHTML = html;
  }

  popover.onclick = (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.step) {
      shown.setMonth(shown.getMonth() + Number(button.dataset.step));
    } else {
      input.value = button.dataset.date ?? "";  // a day, or "" for Clear
      picker.classList.remove("open");
    }
    draw();
  };
  draw();
}

function pad(number) {
  return String(number).padStart(2, "0");
}
