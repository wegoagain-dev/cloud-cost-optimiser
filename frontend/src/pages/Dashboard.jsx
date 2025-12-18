import React, { useState, useEffect } from 'react';
import {
  DollarSign,
  AlertCircle,
  TrendingUp,
  Play,
  Loader,
  Server,
  Database,
  CheckCircle,
  Sparkles,
  Zap,
  Globe
} from 'lucide-react';
import { getDashboardStats, getLatestFindings, triggerScan, getScan } from '../services/api';

const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [findings, setFindings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState('');
  const [selectedRegion, setSelectedRegion] = useState('eu-west-2');

  const regions = [
    { value: 'us-east-1', label: 'US East (N. Virginia)' },
    { value: 'us-east-2', label: 'US East (Ohio)' },
    { value: 'us-west-1', label: 'US West (N. California)' },
    { value: 'us-west-2', label: 'US West (Oregon)' },
    { value: 'eu-west-1', label: 'EU (Ireland)' },
    { value: 'eu-west-2', label: 'EU (London)' },
    { value: 'eu-west-3', label: 'EU (Paris)' },
    { value: 'eu-central-1', label: 'EU (Frankfurt)' },
    { value: 'ap-southeast-1', label: 'Asia Pacific (Singapore)' },
    { value: 'ap-southeast-2', label: 'Asia Pacific (Sydney)' },
    { value: 'ap-northeast-1', label: 'Asia Pacific (Tokyo)' }
  ];

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [statsData, findingsData] = await Promise.all([
        getDashboardStats(),
        getLatestFindings()
      ]);
      setStats(statsData);
      setFindings(findingsData);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleScan = async () => {
    try {
      setScanning(true);
      setScanStatus(`Starting scan in ${selectedRegion}...`);

      const scan = await triggerScan(selectedRegion);
      setScanStatus(`Scanning ${selectedRegion}...`);

      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const updated = await getScan(scan.scan_id);

          if (updated.status === 'completed') {
            clearInterval(pollInterval);
            setScanStatus('✓ Scan complete!');
            setTimeout(() => {
              setScanning(false);
              setScanStatus('');
              loadData();
            }, 2000);
          } else if (updated.status === 'failed') {
            clearInterval(pollInterval);
            setScanStatus('✗ Scan failed');
            setTimeout(() => {
              setScanning(false);
              setScanStatus('');
            }, 3000);
          }
        } catch (err) {
          clearInterval(pollInterval);
          setScanning(false);
          setScanStatus('');
        }
      }, 3000);

    } catch (error) {
      console.error('Scan failed:', error);
      setScanning(false);
      setScanStatus('✗ Failed to start scan');
      setTimeout(() => setScanStatus(''), 3000);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <Loader className="w-12 h-12 animate-spin text-purple-400 mx-auto mb-4" />
          <p className="text-purple-200 text-lg">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const getSeverityColor = (severity) => {
    const colors = {
      critical: 'bg-red-500/20 text-red-300 border-red-500/30',
      high: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
      medium: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
      low: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    };
    return colors[severity] || colors.low;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* Animated background elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }}></div>
      </div>

      {/* Header */}
      <header className="relative backdrop-blur-sm bg-white/5 border-b border-white/10 shadow-2xl">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-gradient-to-br from-purple-500 to-blue-500 rounded-xl shadow-lg">
                <Zap className="w-8 h-8 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold bg-gradient-to-r from-purple-200 via-blue-200 to-purple-200 bg-clip-text text-transparent">
                  Cloud Cost Optimiser
                </h1>
                <p className="text-sm text-purple-300 mt-1 flex items-center space-x-2">
                  <Sparkles className="w-4 h-4" />
                  <span>Intelligent AWS Cost Management</span>
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-4 flex-wrap gap-4">
              {/* Region Selector */}
              <div className="relative">
                <Globe className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-purple-300 pointer-events-none z-10" />
                <select
                  value={selectedRegion}
                  onChange={(e) => setSelectedRegion(e.target.value)}
                  disabled={scanning}
                  className="pl-10 pr-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{ minWidth: '200px' }}
                >
                  {regions.map(region => (
                    <option key={region.value} value={region.value} className="bg-slate-800">
                      {region.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Scan Button */}
              <button
                onClick={handleScan}
                disabled={scanning}
                className={`
                  flex items-center space-x-2 px-6 py-3 rounded-xl font-medium
                  transition-all transform hover:scale-105 shadow-lg
                  ${scanning
                    ? 'bg-gray-700 cursor-not-allowed opacity-50'
                    : 'bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white shadow-purple-500/50'
                  }
                `}
              >
                {scanning ? (
                  <>
                    <Loader className="w-5 h-5 animate-spin" />
                    <span>Scanning...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-5 h-5" />
                    <span>Run Scan</span>
                  </>
                )}
              </button>
            </div>
          </div>
          {scanStatus && (
            <div className="mt-4 px-4 py-2 bg-purple-500/20 border border-purple-500/30 rounded-lg text-purple-200 text-sm inline-flex items-center space-x-2">
              {scanning && <Loader className="w-4 h-4 animate-spin" />}
              <span>{scanStatus}</span>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="relative max-w-7xl mx-auto px-6 py-8">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          {/* Monthly Savings */}
          <div className="group bg-gradient-to-br from-green-500/10 to-emerald-500/10 backdrop-blur-sm rounded-2xl shadow-xl border border-green-500/20 p-6 hover:scale-105 transition-transform duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="p-3 bg-gradient-to-br from-green-500 to-emerald-500 rounded-xl shadow-lg group-hover:shadow-green-500/50 transition-shadow">
                <DollarSign className="w-6 h-6 text-white" />
              </div>
            </div>
            <p className="text-sm text-green-200 mb-2 font-medium">Monthly Savings</p>
            <p className="text-4xl font-bold text-white mb-1">
              {formatCurrency(stats?.total_potential_monthly_savings || 0)}
            </p>
            <p className="text-xs text-green-300">
              {formatCurrency((stats?.total_potential_annual_savings || 0))} annually
            </p>
          </div>

          {/* Recommendations */}
          <div className="group bg-gradient-to-br from-orange-500/10 to-red-500/10 backdrop-blur-sm rounded-2xl shadow-xl border border-orange-500/20 p-6 hover:scale-105 transition-transform duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="p-3 bg-gradient-to-br from-orange-500 to-red-500 rounded-xl shadow-lg group-hover:shadow-orange-500/50 transition-shadow">
                <AlertCircle className="w-6 h-6 text-white" />
              </div>
            </div>
            <p className="text-sm text-orange-200 mb-2 font-medium">Recommendations</p>
            <p className="text-4xl font-bold text-white mb-1">
              {stats?.total_recommendations || 0}
            </p>
            <p className="text-xs text-orange-300">
              {stats?.critical_count || 0} critical, {stats?.high_count || 0} high
            </p>
          </div>

          {/* Implemented */}
          <div className="group bg-gradient-to-br from-blue-500/10 to-cyan-500/10 backdrop-blur-sm rounded-2xl shadow-xl border border-blue-500/20 p-6 hover:scale-105 transition-transform duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="p-3 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl shadow-lg group-hover:shadow-blue-500/50 transition-shadow">
                <CheckCircle className="w-6 h-6 text-white" />
              </div>
            </div>
            <p className="text-sm text-blue-200 mb-2 font-medium">Implemented</p>
            <p className="text-4xl font-bold text-white mb-1">
              {stats?.implemented_count || 0}
            </p>
            <p className="text-xs text-blue-300">
              {formatCurrency(stats?.total_realized_savings || 0)}/mo saved
            </p>
          </div>

          {/* Last Scan */}
          <div className="group bg-gradient-to-br from-purple-500/10 to-pink-500/10 backdrop-blur-sm rounded-2xl shadow-xl border border-purple-500/20 p-6 hover:scale-105 transition-transform duration-300">
            <div className="flex items-center justify-between mb-4">
              <div className="p-3 bg-gradient-to-br from-purple-500 to-pink-500 rounded-xl shadow-lg group-hover:shadow-purple-500/50 transition-shadow">
                <TrendingUp className="w-6 h-6 text-white" />
              </div>
            </div>
            <p className="text-sm text-purple-200 mb-2 font-medium">Last Scan</p>
            <p className="text-xl font-bold text-white mb-1">
              {stats?.last_scan_date
                ? new Date(stats.last_scan_date).toLocaleDateString()
                : 'Never'
              }
            </p>
            <p className="text-xs text-purple-300 flex items-center space-x-1">
              <Globe className="w-3 h-3" />
              <span>Region: {selectedRegion}</span>
            </p>
          </div>
        </div>

        {/* Findings Tables */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* EC2 Findings */}
          <div className="bg-white/5 backdrop-blur-sm rounded-2xl shadow-2xl border border-white/10 overflow-hidden">
            <div className="px-6 py-4 bg-gradient-to-r from-purple-500/20 to-blue-500/20 border-b border-white/10">
              <div className="flex items-center space-x-2">
                <Server className="w-5 h-5 text-purple-300" />
                <h2 className="text-lg font-semibold text-white">
                  EC2 Instances ({findings?.ec2_findings?.length || 0})
                </h2>
              </div>
            </div>
            <div className="p-6 max-h-96 overflow-y-auto">
              {findings?.ec2_findings?.length > 0 ? (
                <div className="space-y-3">
                  {findings.ec2_findings.slice(0, 5).map((finding) => (
                    <div key={finding.id} className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-4 hover:bg-white/10 transition-all duration-300 hover:scale-102">
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <p className="font-medium text-white">{finding.instance_name}</p>
                          <p className="text-sm text-purple-300">{finding.instance_id}</p>
                        </div>
                        <span className={`px-3 py-1 text-xs font-medium rounded-full border ${getSeverityColor(finding.severity)}`}>
                          {finding.severity}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-300">CPU: {finding.avg_cpu}%</span>
                        <span className="font-semibold text-green-400">
                          💰 {formatCurrency(finding.potential_monthly_savings)}/mo
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  <Server className="w-16 h-16 mx-auto mb-4 text-gray-600" />
                  <p className="text-lg">No EC2 findings yet</p>
                  <p className="text-sm mt-2">Run a scan to see recommendations</p>
                </div>
              )}
            </div>
          </div>

          {/* EBS Findings */}
          <div className="bg-white/5 backdrop-blur-sm rounded-2xl shadow-2xl border border-white/10 overflow-hidden">
            <div className="px-6 py-4 bg-gradient-to-r from-blue-500/20 to-cyan-500/20 border-b border-white/10">
              <div className="flex items-center space-x-2">
                <Database className="w-5 h-5 text-blue-300" />
                <h2 className="text-lg font-semibold text-white">
                  EBS Volumes ({findings?.ebs_findings?.length || 0})
                </h2>
              </div>
            </div>
            <div className="p-6 max-h-96 overflow-y-auto">
              {findings?.ebs_findings?.length > 0 ? (
                <div className="space-y-3">
                  {findings.ebs_findings.slice(0, 5).map((finding) => (
                    <div key={finding.id} className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-4 hover:bg-white/10 transition-all duration-300 hover:scale-102">
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <p className="font-medium text-white">
                            {finding.finding_type === 'unattached_volume' ? 'Unattached Volume' : 'Type Optimization'}
                          </p>
                          <p className="text-sm text-blue-300">{finding.resource_id}</p>
                        </div>
                        <span className={`px-3 py-1 text-xs font-medium rounded-full border ${getSeverityColor(finding.severity)}`}>
                          {finding.severity}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-300">
                          {finding.size_gb ? `${finding.size_gb} GB` : 'N/A'}
                        </span>
                        <span className="font-semibold text-green-400">
                          💰 {formatCurrency(finding.potential_monthly_savings)}/mo
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  <Database className="w-16 h-16 mx-auto mb-4 text-gray-600" />
                  <p className="text-lg">No EBS findings yet</p>
                  <p className="text-sm mt-2">Run a scan to see recommendations</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative backdrop-blur-sm bg-white/5 border-t border-white/10 mt-12">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <p className="text-center text-sm text-purple-300">
            Cloud Cost Optimiser v1.0.0 | Powered by FastAPI & React ⚡
          </p>
        </div>
      </footer>
    </div>
  );
};

export default Dashboard;
