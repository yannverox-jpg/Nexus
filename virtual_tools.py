def get_geolocation_data(self, city, country):
    """Traduit la ville et le pays en coordonnées GPS et trouve le fuseau horaire exact."""
    try:
        query = f"{city}, {country}"
        location = self.geolocator.geocode(query)
        if location:
            lat, lon = location.latitude, location.longitude
            timezone = self.tf.timezone_at(lng=lon, lat=lat)
            return {
                "latitude": lat,
                "longitude": lon,
                "timezone": timezone
            }
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Localisation introuvable"}geo = toolkit.get_geolocation_data(profile['city'], profile['country'])geo = toolkit.get_geolocation_data(profile['city'], profile['country'])from faker import Faker
import phonenumbers
from timezonefinder import TimezoneFinder
from geopy.geocoders import Nominatim

class VirtualIdentityToolkit:
    def __init__(self, locale='en_US'):
        # Initialisation de Faker avec la zone géographique souhaitée (ex: 'en_US', 'en_GB')
        self.fake = Faker(locale)
        self.geolocator = Nominatim(user_agent="nexus_bot_geo")
        self.tf = TimezoneFinder()

    def generate_virtual_profile(self):
        """Génère une identité virtuelle complète et cohérente."""
        profile = self.fake.profile()
        address = self.fake.address().replace('\n', ', ')
        
        return {
            "name": profile['name'],
            "username": profile['username'],
            "email": profile['mail'],
            "address": address,
            "city": self.fake.city(),
            "country": self.fake.current_country(),
            "zip_code": self.fake.postcode(),
            "company": profile['company'],
            "birthdate": str(profile['birthdate'])
        }

    def get_virtual_phone(self, country_code="US"):
        """Génère ou formate un numéro de téléphone fictif/virtuel cohérent pour le pays."""
        phone_raw = self.fake.phone_number()
        return f"Numéro virtuel simulé ({country_code}) : {phone_raw}"

    def get_geolocation_data(self, address_string):
        """Traduit une adresse en coordonnées GPS et trouve le fuseau horaire exact."""
        try:
            location = self.geolocator.geocode(address_string)
            if location:
                lat, lon = location.latitude, location.longitude
                timezone = self.tf.timezone_at(lng=lon, lat=lat)
                return {
                    "latitude": lat,
                    "longitude": lon,
                    "timezone": timezone
                }
        except Exception as e:
            return {"error": str(e)}
        return {"error": "Adresse introuvable"}

# --- Test rapide si exécuté directement ---
if __name__ == "__main__":
    toolkit = VirtualIdentityToolkit('en_US')
    
    print("=== TEST DE PROFIL VIRTUEL ===")
    profile = toolkit.generate_virtual_profile()
    for k, v in profile.items():
        print(f"{k}: {v}")
    
    print("\n=== TEST DE GÉOLOCALISATION ===")
    geo = toolkit.get_geolocation_data(profile['address'])
    print(geo)
