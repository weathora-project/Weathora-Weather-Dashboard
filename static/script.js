
document.addEventListener("DOMContentLoaded", function () {
    // Select weather search forms
    const forms = document.querySelectorAll(
        'form[action*="forecast"]'
    );

    forms.forEach(function (form) {
        form.addEventListener("submit", function (event) {
            const cityInput = form.querySelector(
                'input[name="city"]'
            );

            // Check whether city name is entered
            if (cityInput && cityInput.value.trim() === "") {
                event.preventDefault();
                alert("Please enter a city name!");
                cityInput.focus();
                return;
            }

            // Show loading feedback
            const submitButton = form.querySelector(
                'button[type="submit"], input[type="submit"]'
            );

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.dataset.originalText = submitButton.textContent;
                submitButton.innerHTML = "⏳";
                submitButton.setAttribute("aria-label", "Checking weather");
            }
        });
    });

    // Automatically update elements showing the current year
    document.querySelectorAll("[data-current-year]").forEach(
        function (element) {
            element.textContent = new Date().getFullYear();
        }
    );
});
