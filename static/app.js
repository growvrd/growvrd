document.addEventListener('DOMContentLoaded', function() {
    const plantForm = document.getElementById('plant-form');
    const resultsSection = document.getElementById('results');

    // Form submission handler
    plantForm.addEventListener('submit', function(e) {
        e.preventDefault();

        // Collect form data
        const formData = new FormData(plantForm);
        const params = new URLSearchParams();

        for (const [key, value] of formData.entries()) {
            params.append(key, value);
        }

        // Add subscription tier (default to free for demo)
        params.append('subscription_tier', 'free');

        // Show loading state
        resultsSection.innerHTML = '<p class="loading">Finding your perfect plants...</p>';
        resultsSection.classList.remove('hidden');

        // Call the API
        fetch(`/api/recommendations?${params.toString()}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                displayResults(data);
            })
            .catch(error => {
                resultsSection.innerHTML = `<p class="error">Error: ${error.message}</p>`;
            });
    });

    // Display results
    function displayResults(data) {
        // Clear previous results
        resultsSection.innerHTML = '';

        // Create plants section
        const plantsHeading = document.createElement('h2');
        plantsHeading.textContent = 'Your Recommended Plants';
        resultsSection.appendChild(plantsHeading);

        const plantsContainer = document.createElement('div');
        plantsContainer.className = 'results-grid';
        resultsSection.appendChild(plantsContainer);

        // Display plants
        if (data.plants && data.plants.length > 0) {
            data.plants.forEach(plant => {
                const card = document.createElement('div');
                card.className = 'card';

                const image = document.createElement('img');
                image.src = plant.image_url || 'https://via.placeholder.com/300x200?text=Plant+Image';
                image.alt = formatName(plant.name);

                const name = document.createElement('h3');
                name.textContent = formatName(plant.name);

                const scientificName = document.createElement('p');
                scientificName.className = 'scientific-name';
                scientificName.textContent = formatName(plant.scientific_name);

                const description = document.createElement('p');
                description.textContent = plant.description;

                const tags = document.createElement('div');
                tags.className = 'tags';

                const difficultyTag = document.createElement('span');
                difficultyTag.className = 'tag';
                difficultyTag.textContent = `Difficulty: ${plant.difficulty}`;

                const maintenanceTag = document.createElement('span');
                maintenanceTag.className = 'tag';
                maintenanceTag.textContent = `Maintenance: ${plant.maintenance}`;

                tags.appendChild(difficultyTag);
                tags.appendChild(maintenanceTag);

                card.appendChild(image);
                card.appendChild(name);
                card.appendChild(scientificName);
                card.appendChild(description);
                card.appendChild(tags);

                plantsContainer.appendChild(card);
            });
        } else {
            const noPlants = document.createElement('p');
            noPlants.textContent = 'No plants found matching your criteria.';
            plantsContainer.appendChild(noPlants);
        }

        // Create products section if products exist
        if (data.products && data.products.length > 0) {
            const productsHeading = document.createElement('h3');
            productsHeading.textContent = 'Recommended Products';
            resultsSection.appendChild(productsHeading);

            const productsContainer = document.createElement('div');
            productsContainer.className = 'results-grid';
            resultsSection.appendChild(productsContainer);

            data.products.forEach(product => {
                const card = document.createElement('div');
                card.className = 'card product-card';

                const image = document.createElement('img');
                image.src = product.image_url || 'https://via.placeholder.com/300x200?text=Product+Image';
                image.alt = formatName(product.name);

                const name = document.createElement('h3');
                name.textContent = formatName(product.name);

                const description = document.createElement('p');
                description.textContent = product.description;

                const price = document.createElement('p');
                price.className = 'price';
                price.textContent = `$${product.price}`;

                card.appendChild(image);
                card.appendChild(name);
                card.appendChild(description);
                card.appendChild(price);

                productsContainer.appendChild(card);
            });
        }

        // Create kits section if kits exist
        if (data.kits && data.kits.length > 0) {
            const kitsHeading = document.createElement('h3');
            kitsHeading.textContent = 'Plant Care Kits';
            resultsSection.appendChild(kitsHeading);

            const kitsContainer = document.createElement('div');
            kitsContainer.className = 'results-grid';
            resultsSection.appendChild(kitsContainer);

            data.kits.forEach(kit => {
                const card = document.createElement('div');
                card.className = 'card kit-card';

                const image = document.createElement('img');
                image.src = kit.image_url || 'https://via.placeholder.com/300x200?text=Kit+Image';
                image.alt = formatName(kit.name);

                const name = document.createElement('h3');
                name.textContent = formatName(kit.name);

                const description = document.createElement('p');
                description.textContent = kit.difficulty_explanation;

                const price = document.createElement('p');
                price.className = 'price';
                price.textContent = `$${kit.price}`;

                card.appendChild(image);
                card.appendChild(name);
                card.appendChild(description);
                card.appendChild(price);

                kitsContainer.appendChild(card);
            });
        }

        // Show the results section
        resultsSection.classList.remove('hidden');
    }

    // Helper to format names from snake_case to Title Case
    function formatName(name) {
        if (!name) return '';
        return name.split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
    }
});