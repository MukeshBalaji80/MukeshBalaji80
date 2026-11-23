%==============================================================================
% RF_Monitor_Analysis.m
% Path-loss analysis for ESP32 RSSI indoor measurements
% Loads CSV exported from the Flask dashboard, computes statistics, fits
% log-distance path-loss model, and exports grouped statistics.
%
% Workflow:
%   1. Collect data on the dashboard (manual distance labels)
%   2. Export CSV (Time_ms, Distance_m, RSSI_dBm)
%   3. Run this script in MATLAB or MATLAB Online
%   4. Select the CSV file when prompted
%   5. View figures and console output
%   6. Grouped statistics CSV is saved alongside the input file
%==============================================================================

clear; clc; close all;

fprintf('\n============================================================\n');
fprintf('RF Monitor — Indoor Path-Loss Analysis\n');
fprintf('============================================================\n\n');

% ----- 1. Select CSV file -----
[fileName, folderPath] = uigetfile({'*.csv', 'CSV Files (*.csv)'}, ...
    'Select exported RSSI CSV file');
if fileName == 0
    fprintf('No file selected. Exiting.\n');
    return;
end
fullPath = fullfile(folderPath, fileName);
fprintf('Loading: %s\n', fullPath);

% ----- 2. Read and validate CSV -----
% Expected columns: Time_ms, Distance_m, RSSI_dBm
try
    T = readtable(fullPath, 'ReadVariableNames', true);
catch err
    error('Failed to read CSV: %s', err.message);
end

requiredCols = {'Time_ms', 'Distance_m', 'RSSI_dBm'};
missing = requiredCols(~ismember(requiredCols, T.Properties.VariableNames));
if ~isempty(missing)
    error('CSV missing required columns: %s', strjoin(missing, ', '));
end

% Convert to numeric, drop non-numeric rows
for c = requiredCols
    T.(c{1}) = str2double(T.(c{1}));
end

% Count and report dropped rows
before = height(T);
T = rmmissing(T);                % drop rows with NaN in any column
T = T(T.Distance_m > 0, :);      % log10 requires d > 0
after = height(T);
dropped = before - after;
if dropped > 0
    fprintf('Dropped %d invalid/non-numeric or non-positive distance rows.\n', dropped);
end
fprintf('Valid samples remaining: %d\n\n', after);

if after == 0
    error('No valid data after cleaning. Check your CSV.');
end

% ----- 3. Figure A: RSSI vs Time -----
figure('Name', 'A — RSSI vs Time', 'NumberTitle', 'off', 'Position', [100,100,700,400]);
plot(T.Time_ms / 1000, T.RSSI_dBm, 'b.', 'MarkerSize', 6);
xlabel('Time (s)'); ylabel('RSSI (dBm)');
title('RSSI vs Time (raw readings)');
grid on; box on;

% ----- 4. Figure B: RSSI vs Distance (individual) -----
figure('Name', 'B — RSSI vs Distance (all readings)', 'NumberTitle', 'off', 'Position', [850,100,700,400]);
plot(T.Distance_m, T.RSSI_dBm, 'b.', 'MarkerSize', 6);
xlabel('Distance (m)'); ylabel('RSSI (dBm)');
title('RSSI vs Distance (individual readings)');
grid on; box on;

% ----- 5. Group by distance -----
% Use unique distances as groups
uniqueDist = unique(T.Distance_m);
nGroups = numel(uniqueDist);

% Build statistics table
stats = table('Size', [nGroups, 4], 'VariableTypes', {'double','double','double','double'}, ...
    'VariableNames', {'Distance_m', 'Mean_RSSI_dBm', 'Std_RSSI_dBm', 'N_Samples'});
stats.Distance_m = uniqueDist;

fprintf('\n--- Group Statistics (per distance) ---\n');
fprintf('%12s  %14s  %12s  %10s\n', 'Distance(m)', 'Mean(dBm)', 'Std(dBm)', 'N');

for i = 1:nGroups
    d = uniqueDist(i);
    mask = (T.Distance_m == d);
    group = T.RSSI_dBm(mask);
    n = numel(group);
    stats.N_Samples(i) = n;
    stats.Mean_RSSI_dBm(i) = mean(group);
    if n > 1
        stats.Std_RSSI_dBm(i) = std(group);
    else
        stats.Std_RSSI_dBm(i) = NaN; % undefined for N=1
    end
    if n > 1
        fprintf('%12.3f  %14.2f  %12.2f  %10d\n', d, stats.Mean_RSSI_dBm(i), stats.Std_RSSI_dBm(i), n);
    else
        fprintf('%12.3f  %14.2f  %12s  %10d\n', d, stats.Mean_RSSI_dBm(i), 'N/A', n);
    end
end

% ----- 6. Figure C: Table per distance (display in console, also figure) -----
figure('Name', 'C — Per-Distance Statistics', 'NumberTitle', 'off', 'Position', [100,550,700,400]);
% Render table as an image in a figure
uitable('Data', stats{:,:}, 'ColumnName', stats.Properties.VariableNames, ...
    'Position', [20, 20, 660, 360], 'ColumnEditable', false);

% ----- 7. Figure D: Mean RSSI vs Distance with error bars -----
figure('Name', 'D — Mean RSSI vs Distance (with error bars)', 'NumberTitle', 'off', 'Position', [850,550,700,400]);
% Only plot groups with N > 1 for error bars
validGroups = stats.N_Samples > 1;
if any(validGroups)
    errorbar(stats.Distance_m(validGroups), stats.Mean_RSSI_dBm(validGroups), ...
        stats.Std_RSSI_dBm(validGroups), 'bo-', 'MarkerFaceColor', 'b', 'LineWidth', 1.5);
    hold on;
end
% Plot N=1 points without error bars
singleGroups = stats.N_Samples == 1;
if any(singleGroups)
    plot(stats.Distance_m(singleGroups), stats.Mean_RSSI_dBm(singleGroups), 'rs', ...
        'MarkerFaceColor', 'r', 'MarkerSize', 8, 'DisplayName', 'N=1 (no std)');
end
xlabel('Distance (m)'); ylabel('Mean RSSI (dBm)');
title('Mean RSSI vs Distance with Std Error Bars');
grid on; box on; legend show;

% ----- 8. Fit log-distance path-loss model -----
% Model: RSSI(d) = A + B * log10(d)
% Path-loss exponent: n = -B / 10
% Use ONLY groups with N >= 2 (or all points? We'll use group means with N>=2).
fprintf('\n--- Path-Loss Model Fit ---\n');
fitGroups = stats.N_Samples >= 2;
if sum(fitGroups) >= 2
    x = log10(stats.Distance_m(fitGroups));
    y = stats.Mean_RSSI_dBm(fitGroups);
    % Linear regression: y = A + B * x
    p = polyfit(x, y, 1); % p(1)=B (slope), p(2)=A (intercept)
    B = p(1);
    A = p(2);
    y_fit = A + B * x;
    SS_res = sum((y - y_fit).^2);
    SS_tot = sum((y - mean(y)).^2);
    R2 = 1 - SS_res / SS_tot;
    n = -B / 10;

    fprintf('Using %d distance groups (N >= 2 per group)\n', sum(fitGroups));
    fprintf('Model: RSSI(d) = A + B * log10(d)\n');
    fprintf('Intercept A = %.3f dBm\n', A);
    fprintf('Slope     B = %.3f dBm/decade\n', B);
    fprintf('Path-loss exponent n = -B/10 = %.3f\n', n);
    fprintf('R-squared = %.4f\n', R2);

    % ----- 9. Figure E: Fitted model over measured data -----
    figure('Name', 'E — Fitted Path-Loss Model', 'NumberTitle', 'off', 'Position', [100,1000,700,400]);
    % Measured means with error bars
    errorbar(stats.Distance_m(validGroups), stats.Mean_RSSI_dBm(validGroups), ...
        stats.Std_RSSI_dBm(validGroups), 'bo', 'MarkerFaceColor', 'b', 'LineWidth', 1.5);
    hold on;
    if any(singleGroups)
        plot(stats.Distance_m(singleGroups), stats.Mean_RSSI_dBm(singleGroups), 'rs', ...
            'MarkerFaceColor', 'r', 'MarkerSize', 8, 'DisplayName', 'N=1 (no std)');
    end
    % Fitted curve
    d_fine = linspace(min(stats.Distance_m), max(stats.Distance_m), 200);
    rssi_fine = A + B * log10(d_fine);
    plot(d_fine, rssi_fine, 'k-', 'LineWidth', 2, 'DisplayName', 'Fitted model');
    xlabel('Distance (m)'); ylabel('RSSI (dBm)');
    title(sprintf('Fitted: RSSI = %.2f + %.2f * log10(d)  (n=%.3f, R^2=%.3f)', A, B, n, R2));
    grid on; box on; legend show;
else
    warning('Fewer than 2 distance groups with N>=2 samples. Cannot fit path-loss model.\n');
    fprintf('WARNING: Need at least 2 distances with >=2 samples each for fitting.\n');
    fprintf('Skipping model fit and Figure E.\n');
    n = NaN; A = NaN; B = NaN; R2 = NaN;
end

% ----- 10. Export grouped statistics to CSV -----
[~, baseName, ~] = fileparts(fileName);
outFile = fullfile(folderPath, [baseName, '_grouped_stats.csv']);
writetable(stats, outFile);
fprintf('\nGrouped statistics exported to: %s\n', outFile);

fprintf('\n============================================================\n');
fprintf('Analysis complete.\n');
fprintf('============================================================\n');