from django.contrib import admin

from fridge.models import ShoppingList, Product

admin.site.register(Product)
admin.site.register(ShoppingList)
