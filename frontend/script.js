const form = document.getElementById('prediction-form');
const result = document.getElementById('result');
const predictionEmpty = document.getElementById('prediction-empty');
const resultBadge = document.getElementById('result-badge');
const checkAccuracyButton = document.getElementById('check-accuracy-btn');
const accuracyResult = document.getElementById('accuracy-result');

const searchCitySelect = document.getElementById('search-city');
const searchBranchSelect = document.getElementById('search-branch');
const searchTypeSelect = document.getElementById('search-type');
const searchBoysHostelSelect = document.getElementById('search-boys-hostel');
const searchGirlsHostelSelect = document.getElementById('search-girls-hostel');
const searchRecommendationsButton = document.getElementById('search-recommendations-btn');
const recommendationResults = document.getElementById('recommendation-results');
const recommendationCount = document.getElementById('recommendation-count');
const recommendationNote = document.getElementById('recommendation-note');

const categorySelect = document.getElementById('category');
const quotaSelect = document.getElementById('quota');
const citySelect = document.getElementById('filter-city');
const branchSelect = document.getElementById('filter-branch');
const boysHostelSelect = document.getElementById('filter-boys-hostel');
const girlsHostelSelect = document.getElementById('filter-girls-hostel');
const filterForm = document.getElementById('filter-form');
const filterResults = document.getElementById('filter-results');

const DEFAULT_PAGE_SIZE = '10';
let currentPredictionRows = [];
let currentPredictionData = null;
let activeFilters = {};
let isFetchingPage = false;
let lastFilterKey = '';
const institutePageCache = new Map();

function setPredictionState(message, isSuccess = false) {
  result.textContent = message;
  if (predictionEmpty) {
    predictionEmpty.style.display = isSuccess ? 'none' : 'block';
  }
  if (resultBadge) {
    resultBadge.textContent = isSuccess ? 'Prediction Ready' : 'Awaiting Input';
    resultBadge.classList.toggle('success', isSuccess);
  }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"]|'/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[character]));
}

function getOptionalIntegerValue(element) {
  if (!element) {
    return null;
  }

  const value = String(element.value ?? '').trim();
  if (!value) {
    return null;
  }

  const parsedValue = Number.parseInt(value, 10);
  return Number.isFinite(parsedValue) ? parsedValue : null;
}

function setRecommendationSummary(count, note) {
  if (recommendationCount) {
    recommendationCount.textContent = `${count} match${count === 1 ? '' : 'es'}`;
  }
  if (recommendationNote) {
    recommendationNote.textContent = note;
  }
}

function renderRecommendationRows(rows) {
  if (!recommendationResults) {
    return;
  }

  if (!rows.length) {
    recommendationResults.innerHTML = '<tr><td colspan="6">No verified institutes matched the current search filters.</td></tr>';
    return;
  }

  recommendationResults.innerHTML = rows.map((row, index) => {
    const websiteLink = row.official_website
      ? `<a href="${escapeHtml(row.official_website)}" target="_blank" rel="noreferrer">Visit</a>`
      : '<span class="muted-link">Not listed</span>';
    const branch = row.course_name || row.admission_field || '-';

    return `
      <tr>
        <td>${index + 1}</td>
        <td>${escapeHtml(row.institute_name)}</td>
        <td>${escapeHtml(branch)}</td>
        <td>${escapeHtml(row.college_type)}</td>
        <td>${escapeHtml(row.tuition_fee)}</td>
        <td>${websiteLink}</td>
      </tr>
    `;
  }).join('');
}

function collectPredictionPayload() {
  return {
    rank: document.getElementById('rank').value,
    category: categorySelect.value || null,
    quota: quotaSelect.value || null,
  };
}

function normalizeText(value) {
  return String(value ?? '').trim().toLowerCase();
}

function applyRecommendationFilters() {
  const filters = {
    city: searchCitySelect ? searchCitySelect.value.trim() : '',
    branch: searchBranchSelect ? searchBranchSelect.value.trim() : '',
    collegeType: searchTypeSelect ? searchTypeSelect.value.trim() : '',
    boysHostel: searchBoysHostelSelect ? searchBoysHostelSelect.value.trim() : '',
    girlsHostel: searchGirlsHostelSelect ? searchGirlsHostelSelect.value.trim() : '',
  };

  let rows = [...currentPredictionRows];

  if (filters.city) {
    rows = rows.filter((row) => normalizeText(row.city) === normalizeText(filters.city));
  }
  if (filters.branch) {
    rows = rows.filter((row) => normalizeText(row.course_name || row.admission_field) === normalizeText(filters.branch));
  }
  if (filters.collegeType) {
    rows = rows.filter((row) => normalizeText(row.college_type) === normalizeText(filters.collegeType));
  }
  if (filters.boysHostel) {
    rows = rows.filter((row) => normalizeText(row.boys_hostel) === normalizeText(filters.boysHostel));
  }
  if (filters.girlsHostel) {
    rows = rows.filter((row) => normalizeText(row.girls_hostel) === normalizeText(filters.girlsHostel));
  }

  renderRecommendationRows(rows);

  if (!currentPredictionData) {
    setRecommendationSummary(0, 'Run a prediction to see verified institute matches.');
    return;
  }

  const predictedField = currentPredictionData.predicted_field || 'the selected field';
  const filterFragments = [];
  if (filters.city) filterFragments.push(`city ${filters.city}`);
  if (filters.branch) filterFragments.push(`branch ${filters.branch}`);
  if (filters.collegeType) filterFragments.push(`type ${filters.collegeType}`);
  if (filters.boysHostel) filterFragments.push(`boys hostel ${filters.boysHostel}`);
  if (filters.girlsHostel) filterFragments.push(`girls hostel ${filters.girlsHostel}`);

  const filterText = filterFragments.length ? ` after filtering by ${filterFragments.join(', ')}` : '';
  const baseText = currentPredictionData.matched_predicted_field === false
    ? `The predicted field ${predictedField} had no direct fee-dataset match, so these are the nearest verified options.`
    : `These are verified institutes for ${predictedField}.`;

  setRecommendationSummary(
    rows.length,
    `${rows.length} verified institute${rows.length === 1 ? '' : 's'} matched${filterText}. ${baseText}`
  );
}

function loadSelectOptions(selectElement, options, placeholder) {
  if (!selectElement) {
    return;
  }

  selectElement.innerHTML = `<option value="">${placeholder}</option>`;
  [...new Set(options)].forEach((optionValue) => {
    const option = document.createElement('option');
    option.value = optionValue;
    option.textContent = optionValue;
    selectElement.appendChild(option);
  });
}

function loadStaticSearchOptions() {
  if (searchTypeSelect) {
    searchTypeSelect.innerHTML = `
      <option value="">All Types</option>
      <option value="Govt">Govt</option>
      <option value="GIA">GIA</option>
      <option value="SFI">SFI</option>
    `;
  }

  if (searchBoysHostelSelect) {
    searchBoysHostelSelect.innerHTML = `
      <option value="">All</option>
      <option value="Yes">Yes</option>
      <option value="No">No</option>
    `;
  }

  if (searchGirlsHostelSelect) {
    searchGirlsHostelSelect.innerHTML = `
      <option value="">All</option>
      <option value="Yes">Yes</option>
      <option value="No">No</option>
    `;
  }
}

async function loadFilterOptions() {
  const response = await fetch('/api/options');
  const data = await response.json();

  if (Array.isArray(data.categories)) {
    loadSelectOptions(categorySelect, data.categories, 'Auto');
  }

  if (Array.isArray(data.quotas)) {
    loadSelectOptions(quotaSelect, data.quotas, 'Auto');
  }

  if (Array.isArray(data.cities)) {
    loadSelectOptions(searchCitySelect, data.cities, 'All Cities');
  }

  if (Array.isArray(data.branches)) {
    loadSelectOptions(searchBranchSelect, data.branches, 'All Branches');
  }

  loadStaticSearchOptions();
  setPredictionState('No prediction yet.', false);
  setRecommendationSummary(0, 'Run a prediction to see verified institute matches.');
  renderRecommendationRows([]);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();

  const payload = collectPredictionPayload();

  try {
    setPredictionState('Predicting...', false);
    setRecommendationSummary(0, 'Fetching verified institute matches...');

    const response = await fetch('/predict', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();

    if (!response.ok) {
      setPredictionState(data.error || 'Prediction failed.', false);
      currentPredictionRows = [];
      currentPredictionData = null;
      renderRecommendationRows([]);
      setRecommendationSummary(0, data.error || 'No verified recommendations available.');
      return;
    }

    currentPredictionRows = Array.isArray(data.eligible_institutes) ? data.eligible_institutes : [];
    currentPredictionData = data;
    setPredictionState(data.predicted_field || 'Prediction completed.', true);
    applyRecommendationFilters();
  } catch (error) {
    setPredictionState('Unable to connect to the backend.', false);
    currentPredictionRows = [];
    currentPredictionData = null;
    renderRecommendationRows([]);
    setRecommendationSummary(0, 'Unable to load verified institute matches.');
  }
});

if (checkAccuracyButton) {
  checkAccuracyButton.addEventListener('click', async () => {
    const payload = collectPredictionPayload();

    try {
      if (accuracyResult) {
        accuracyResult.textContent = 'Checking accuracy...';
      }

      const response = await fetch('/predict/check', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (!response.ok) {
        if (accuracyResult) {
          accuracyResult.textContent = data.error || 'Accuracy check failed.';
        }
        return;
      }

      const estimatedInputAccuracy = typeof data.estimated_input_accuracy === 'number'
        ? `${(data.estimated_input_accuracy * 100).toFixed(2)}%`
        : 'N/A';
      const modelAccuracy = typeof data.model_training_accuracy === 'number'
        ? `${(data.model_training_accuracy * 100).toFixed(2)}%`
        : 'N/A';
      const similarRows = data.similar_rows_used || 0;
      const rankWindow = data.rank_window || 0;

      if (accuracyResult) {
        const accuracyInfo = document.getElementById('accuracy-info');
        const accuracyMetrics = document.getElementById('accuracy-metrics');
        
        // Create metrics display
        const metricsHtml = `
          <div class="accuracy-metric">
            <span class="accuracy-metric-label">Predicted Field:</span>
            <span class="accuracy-metric-value">${escapeHtml(data.predicted_field)}</span>
          </div>
          <div class="accuracy-metric">
            <span class="accuracy-metric-label">Estimated Input Accuracy:</span>
            <span class="accuracy-metric-value">${estimatedInputAccuracy}</span>
          </div>
          <div class="accuracy-metric">
            <span class="accuracy-metric-label">Model Training Accuracy:</span>
            <span class="accuracy-metric-value">${modelAccuracy}</span>
          </div>
          <div class="accuracy-metric">
            <span class="accuracy-metric-label">Similar Ranks Found:</span>
            <span class="accuracy-metric-value">${similarRows}</span>
          </div>
          <div class="accuracy-metric">
            <span class="accuracy-metric-label">Rank Window:</span>
            <span class="accuracy-metric-value">±${rankWindow}</span>
          </div>
        `;
        
        if (accuracyMetrics) {
          accuracyMetrics.innerHTML = metricsHtml;
          if (accuracyInfo) {
            accuracyInfo.style.display = 'block';
          }
        }
        
        accuracyResult.textContent = `✓ Accuracy checked for ${data.predicted_field}`;
      }
    } catch (error) {
      if (accuracyResult) {
        accuracyResult.textContent = 'Unable to connect to the backend.';
      }
    }
  });
}

if (searchRecommendationsButton) {
  searchRecommendationsButton.addEventListener('click', () => {
    applyRecommendationFilters();
  });
}

// Optional search form for other colleges
const searchInstituteForm = document.getElementById('institute-search-form');
const searchInstituteNameInput = document.getElementById('search-institute-name');
const searchOtherBranchSelect = document.getElementById('search-other-branch');
const searchOtherCitySelect = document.getElementById('search-other-city');
const searchOtherInstitutesButton = document.getElementById('search-other-institutes-btn');
const otherSearchResults = document.getElementById('other-search-results');
const otherSearchCount = document.getElementById('other-search-count');
const otherSearchResultsTbody = document.getElementById('other-search-results-tbody');

function renderOtherSearchResults(rows) {
  if (!otherSearchResultsTbody) return;

  if (!rows || !rows.length) {
    otherSearchResultsTbody.innerHTML = '<tr><td colspan="6">No institutes found matching your search criteria.</td></tr>';
    return;
  }

  otherSearchResultsTbody.innerHTML = rows.map((row, index) => {
    const websiteLink = row.official_website
      ? `<a href="${escapeHtml(row.official_website)}" target="_blank" rel="noreferrer">Visit</a>`
      : '<span class="muted-link">Not listed</span>';
    const branch = row.course_name || row.admission_field || '-';

    return `
      <tr>
        <td>${index + 1}</td>
        <td>${escapeHtml(row.institute_name)}</td>
        <td>${escapeHtml(branch)}</td>
        <td>${escapeHtml(row.college_type)}</td>
        <td>${escapeHtml(row.city)}</td>
        <td>${websiteLink}</td>
      </tr>
    `;
  }).join('');
}

async function initializeSearchForm() {
  // Load options for search form
  const response = await fetch('/api/options');
  const data = await response.json();

  if (Array.isArray(data.branches) && searchOtherBranchSelect) {
    loadSelectOptions(searchOtherBranchSelect, data.branches, 'All Branches');
  }

  if (Array.isArray(data.cities) && searchOtherCitySelect) {
    loadSelectOptions(searchOtherCitySelect, data.cities, 'All Cities');
  }
}

if (searchOtherInstitutesButton) {
  searchOtherInstitutesButton.addEventListener('click', async () => {
    const instituteName = searchInstituteNameInput ? searchInstituteNameInput.value.trim() : '';
    const branchFilter = searchOtherBranchSelect ? searchOtherBranchSelect.value.trim() : '';
    const cityFilter = searchOtherCitySelect ? searchOtherCitySelect.value.trim() : '';

    if (!instituteName && !branchFilter && !cityFilter) {
      if (otherSearchCount) {
        otherSearchCount.textContent = '0 matches';
      }
      renderOtherSearchResults([]);
      return;
    }

    try {
      if (otherSearchCount) {
        otherSearchCount.textContent = 'Searching...';
      }

      const queryParams = new URLSearchParams();
      if (instituteName) queryParams.append('institute_name', instituteName);
      if (branchFilter) queryParams.append('branch', branchFilter);
      if (cityFilter) queryParams.append('city', cityFilter);

      const response = await fetch(`/api/search-institutes?${queryParams.toString()}`);
      const data = await response.json();

      if (!response.ok) {
        if (otherSearchCount) {
          otherSearchCount.textContent = '0 matches';
        }
        renderOtherSearchResults([]);
        return;
      }

      const results = Array.isArray(data.results) ? data.results : [];
      if (otherSearchCount) {
        otherSearchCount.textContent = `${results.length} match${results.length === 1 ? '' : 'es'}`;
      }

      renderOtherSearchResults(results);
      if (otherSearchResults) {
        otherSearchResults.style.display = results.length > 0 ? 'block' : 'none';
      }
    } catch (error) {
      console.error('Search failed:', error);
      if (otherSearchCount) {
        otherSearchCount.textContent = '0 matches';
      }
      renderOtherSearchResults([]);
    }
  });
}

loadFilterOptions().catch(() => {
  if (categorySelect) categorySelect.innerHTML = '<option value="">Unable to load categories</option>';
  if (quotaSelect) quotaSelect.innerHTML = '<option value="">Unable to load quotas</option>';
  if (searchCitySelect) searchCitySelect.innerHTML = '<option value="">Unable to load cities</option>';
  if (searchBranchSelect) searchBranchSelect.innerHTML = '<option value="">Unable to load branches</option>';
});

initializeSearchForm().catch(() => {
  if (searchOtherBranchSelect) searchOtherBranchSelect.innerHTML = '<option value="">Unable to load branches</option>';
  if (searchOtherCitySelect) searchOtherCitySelect.innerHTML = '<option value="">Unable to load cities</option>';
});
